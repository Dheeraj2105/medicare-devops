from triage import create_triage_blueprint  # noqa: E402
app.register_blueprint(create_triage_blueprint(get_db, patient_dict, APP_VERSION, APP_COLOR))
