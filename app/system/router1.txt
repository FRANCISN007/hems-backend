import subprocess
from fastapi import APIRouter

router = APIRouter()

@router.post("/update-app")
def update_app():
    """Run the BAT file to copy build folder into Program Files."""
    try:
        # Path to your .bat updater
        bat_path = r"C:\Users\KLOUNGE\Documents\HEMS-PROJECT\update-react-build.bat"

        # Run the BAT file
        result = subprocess.run(
            ["cmd.exe", "/c", bat_path],
            capture_output=True,
            text=True,
            timeout=30  # ⏱ stop after 30s
        )


        if result.returncode != 0:
            return {
                "status": "error",
                "message": "Update failed",
                "stderr": result.stderr,
                "stdout": result.stdout,
            }

        return {
            "status": "success",
            "message": "✅ Update successful!",
            "stdout": result.stdout,
        }

    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}
