"""Development entry point: ``python run.py``. Set PORT to use something other than 5000."""

import os

from anga import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
