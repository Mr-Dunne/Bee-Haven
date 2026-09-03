import os

from flask import Flask

from models import db

app = Flask(__name__, instance_relative_config=True)

# instance/ is gitignored, so the SQLite file itself never gets committed.
os.makedirs(app.instance_path, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "beehaven.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


@app.route('/')
def home():
    return "Bee-Haven Online"


if __name__ == "__main__":
    app.run(debug=True)