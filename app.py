import os
import sys
import click
from datetime import date
from io import BytesIO
from flask import Flask, abort, render_template, request, send_file, send_from_directory, url_for
from flask_login import current_user
from sqlalchemy.engine import make_url
from config import Config, DATA_DIR
from extensions import db, login_manager, csrf
from utils.uploads import read_upload, upload_mimetype


def create_app(overrides=None):
    kwargs = {}
    if getattr(sys, "frozen", False):
        root = sys._MEIPASS
        kwargs["template_folder"] = os.path.join(root, "templates")
        kwargs["static_folder"] = os.path.join(root, "static")
    elif Config.IS_VERCEL:
        kwargs["static_folder"] = None
    app = Flask(__name__, **kwargs)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    if app.config["IS_VERCEL"]:
        required = {
            "SUPABASE_URL": app.config["SUPABASE_URL"],
            "SUPABASE_SERVICE_ROLE_KEY": app.config["SUPABASE_SERVICE_ROLE_KEY"],
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError("Missing Vercel environment variable(s): " + ", ".join(missing))
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://"):
            raise RuntimeError("Vercel deployment requires a Supabase PostgreSQL DATABASE_URL.")
        if make_url(app.config["SQLALCHEMY_DATABASE_URI"]).query.get("sslmode") != "require":
            raise RuntimeError("Set sslmode=require in the Supabase DATABASE_URL.")
        if not app.config["SESSION_COOKIE_SECURE"]:
            raise RuntimeError("Set SESSION_COOKIE_SECURE=1 in Vercel.")
        if len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"] == "dev-only-change-me":
            raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters.")
        owner_username = os.getenv("OWNER_USERNAME", "")
        owner_password = os.getenv("OWNER_PASSWORD", "")
        if not owner_username or owner_username.startswith("REPLACE_"):
            raise RuntimeError("Set OWNER_USERNAME in Vercel.")
        if len(owner_password) < 12 or owner_password.startswith("REPLACE_"):
            raise RuntimeError("Set a unique OWNER_PASSWORD of at least 12 characters in Vercel.")
    elif app.config["UPLOAD_STORAGE_BACKEND"] == "local":
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"

    from models import User, Institute

    @login_manager.user_loader
    def load_user(uid):
        u = db.session.get(User, int(uid))
        return u if u and u.active else None

    from routes import register_blueprints
    register_blueprints(app)

    if app.config["IS_VERCEL"]:
        app.add_url_rule(
            "/static/<path:filename>",
            endpoint="static",
            view_func=lambda filename: abort(404),
        )

    @app.route("/uploads/<path:name>")
    def uploaded_file(name):
        if os.path.basename(name) != name:
            abort(404)
        if app.config["UPLOAD_STORAGE_BACKEND"] == "supabase":
            return send_file(
                BytesIO(read_upload(name)),
                mimetype=upload_mimetype(name),
                max_age=0,
            )
        return send_from_directory(app.config["UPLOAD_FOLDER"], name)

    # ---- template helpers ----
    app.jinja_env.filters["zip"] = lambda a, *b: zip(a, *b)
    app.jinja_env.filters["inr"] = lambda v: "Rs. {:,.2f}".format(v or 0)
    app.jinja_env.filters["dmy"] = lambda d: d.strftime("%d %b %Y") if d else "-"
    app.jinja_env.filters["tfmt"] = lambda t: t.strftime("%I:%M %p") if t else "-"
    app.jinja_env.globals["page_url"] = lambda n: url_for(
        request.endpoint, **{**(request.view_args or {}), **request.args.to_dict(), "page": n})

    @app.context_processor
    def inject_globals():
        ctx = {"today": date.today(), "inst": None, "notifs": []}
        try:
            ctx["inst"] = Institute.query.first()
            if current_user.is_authenticated:
                from services import notification_items
                ctx["notifs"] = notification_items()
        except Exception:
            db.session.rollback()
        return ctx

    # ---- safe error handling ----
    @app.errorhandler(403)
    def e403(e):
        return render_template("error.html", code=403, title="Access denied",
                               msg="You do not have permission to open this page."), 403

    @app.errorhandler(404)
    def e404(e):
        return render_template("error.html", code=404, title="Page not found",
                               msg="The page you are looking for does not exist."), 404

    @app.errorhandler(413)
    def e413(e):
        return render_template("error.html", code=413, title="File too large", msg="Please upload a file under 2 MB."), 413

    @app.errorhandler(500)
    def e500(e):
        db.session.rollback()
        return render_template("error.html", code=500, title="Something went wrong",
                               msg="Please try again. If the problem continues, contact your administrator."), 500

    # ---- CLI ----
    @app.cli.command("init-db")
    def init_db():
        """Create tables, the institute row and the first owner account."""
        created = ensure_database(app)
        if created:
            click.echo(f"Owner account created: {created}")
        click.echo("Database ready.")

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """DEVELOPMENT ONLY: load sample courses, batches, students, fees and attendance."""
        from seed_demo import seed
        seed()

    @app.cli.command("check-server-config")
    def check_server_config():
        """Validate the minimum configuration for the shared Windows server launcher."""
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql+pymysql://"):
            raise click.ClickException("Shared server mode requires MySQL; SQLite is for single-PC use only.")
        if len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"] == "dev-only-change-me":
            raise click.ClickException("Set SECRET_KEY to a random value of at least 32 characters in .env.")
        owner_password = os.getenv("OWNER_PASSWORD", "ChangeMe@123")
        if len(owner_password) < 12 or owner_password == "ChangeMe@123":
            raise click.ClickException("Set a unique OWNER_PASSWORD of at least 12 characters in .env.")
        click.echo("Shared server configuration looks ready.")

    @app.cli.command("check-deployment-config")
    def check_deployment_config():
        """Validate required settings before deploying TypeTrack to a public host."""
        database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
        supported_database = database_uri.startswith((
            "mysql+pymysql://",
            "postgresql+psycopg://",
        ))
        if not supported_database:
            raise click.ClickException(
                "Hosted deployment requires MySQL or PostgreSQL. Configure DATABASE_URL "
                "with a mysql+pymysql:// or postgresql+psycopg:// scheme, or set the DB_* variables."
            )
        secret_key = app.config["SECRET_KEY"]
        if len(secret_key) < 32 or secret_key == "dev-only-change-me" or secret_key.startswith("REPLACE_"):
            raise click.ClickException("Set SECRET_KEY to a random value of at least 32 characters.")
        owner_username = os.getenv("OWNER_USERNAME", "")
        if not owner_username or owner_username.startswith("REPLACE_"):
            raise click.ClickException("Set OWNER_USERNAME to the initial owner login.")
        owner_password = os.getenv("OWNER_PASSWORD", "")
        if len(owner_password) < 12 or owner_password == "ChangeMe@123" or owner_password.startswith("REPLACE_"):
            raise click.ClickException("Set OWNER_PASSWORD to a unique password of at least 12 characters.")
        if not app.config["SESSION_COOKIE_SECURE"]:
            raise click.ClickException("Set SESSION_COOKIE_SECURE=1 after HTTPS is enabled.")
        click.echo("Hosted deployment configuration looks ready.")

    return app


def ensure_database(app):
    """Create tables and the first owner if this PC has no data yet. Returns the new username, or None."""
    from models import Institute, User

    with app.app_context():
        db.create_all()
        if not Institute.query.first():
            institute = Institute(
                name=app.config["INSTITUTE_NAME"],
                owner_name=app.config["INSTITUTE_OWNER_NAME"],
                address=app.config["INSTITUTE_ADDRESS"],
                phone=app.config["INSTITUTE_PHONE"],
                email=app.config["INSTITUTE_EMAIL"],
                website=app.config["INSTITUTE_WEBSITE"],
            )
            if app.config["INSTITUTE_RECEIPT_NOTE"]:
                institute.receipt_note = app.config["INSTITUTE_RECEIPT_NOTE"]
            db.session.add(institute)
        created = None
        if not User.query.filter_by(role="owner").first():
            created = os.getenv("OWNER_USERNAME", "admin")
            u = User(name=os.getenv("OWNER_NAME", "Institute Owner"), username=created, role="owner")
            u.set_password(os.getenv("OWNER_PASSWORD", "ChangeMe@123"))
            db.session.add(u)
        db.session.commit()
        if created:
            from config import DATA_DIR
            note = os.path.join(DATA_DIR, "first-login.txt")
            if not os.path.exists(note):
                with open(note, "w", encoding="utf-8") as f:
                    f.write(
                        "TypeTrack owner login for this computer\n"
                        f"Username: {created}\n"
                        f"Password: {os.getenv('OWNER_PASSWORD', 'ChangeMe@123')}\n"
                        "Change this password after the first login, then delete this file.\n"
                    )
        return created


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
