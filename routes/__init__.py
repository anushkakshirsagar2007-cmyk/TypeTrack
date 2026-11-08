def register_blueprints(app):
    from routes import auth, dashboard, students, inquiries, batches, attendance, fees, reports, settings, search
    for m in (auth, dashboard, students, inquiries, batches, attendance, fees, reports, settings, search):
        app.register_blueprint(m.bp)
