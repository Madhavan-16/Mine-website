"""Development entry point for MiNe."""
from mine import create_app

app = create_app()

if __name__ == "__main__":
    print("MiNe dev server — open http://127.0.0.1:5000 (port 5000 is required)")
    app.run(host="0.0.0.0", port=5000, debug=True)