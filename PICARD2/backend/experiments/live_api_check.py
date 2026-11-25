# - Log in
# - Check experiment history. Empty
# - Check datasets. Empty + public
# - Check scripts. Empty + public
# - Add dataset D.
# - Check datasets. D + public
# - Add script P (py).
# - Add script J (jar).
# - Check scripts. P + J + public
# - Create experiment D + P = E.
# - Check experiments.  E running
# - Watch E for passphrase.
# - Check until E is complete.
# - Get E results: Check against expected
# - Check experiments. E not running.
# - Check datasets. D + public
# - Check scripts. S + public
# - Delete D.
# - Delete S.
# - Check datasets. Empty + public
# - Check scripts. Empty + public
# - Log out.
# - Check datasets. Not allowed
# - Check scripts. Not allowed
# - Check experiments. Not allowed
# experiments/live_api_check.py
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
base_url = os.environ.get('BACKEND_LOCAL_URL')
if not base_url:
    raise RuntimeError("BACKEND_LOCAL_URL must be set in backend/.env or the environment.")
base_url = base_url.rstrip('/')

# 2. Use a Session object to persist cookies (like sessionid and csrftoken)
session = requests.Session()

# 3. Define the data you want to send
user_data = {
    "username": "testuser_api",
    "password": "testpassword123"
}


def test_signup():
    print("\n--- 1. Signing up ---")
    response = session.post(f"{base_url}/auth/signup/", json=user_data)

    if response.status_code in [200, 201]:
        print("✅ Success:", response.json())
    else:
        print(f"❌ Failed signup (Status {response.status_code}):", response.text)


def test_login():
    print("\n--- 2. Logging in ---")
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = session.post(f"{base_url}/auth/user_login/", json=login_data)

    if response.status_code == 200:
        print("✅ Success:", response.json())

        # Django session auth requires the CSRF token for subsequent POST requests
        if 'csrftoken' in session.cookies:
            session.headers.update({'X-CSRFToken': session.cookies['csrftoken']})
    else:
        print(f"❌ Failed login (Status {response.status_code}):", response.text)


def test_upload_dataset():
    print("\n--- 3. Uploading Dataset ---")
    # Create a temporary dummy CSV file
    filename = "dummy_dataset.csv"
    with open(filename, "w") as f:
        f.write("col1,col2\n10,20\n30,40")

    with open(filename, "rb") as f:
        # 'file' matches the request.FILES.get('file') in views.py
        files = {'file': (filename, f, 'text/csv')}
        data = {'access_modifier': 'private'}
        response = session.post(f"{base_url}/datasets/upload/csv/", files=files, data=data)

    os.remove(filename)  # Clean up the dummy file

    if response.status_code in [200, 201]:
        res_data = response.json()
        print("✅ Success:", res_data)
        return res_data.get('data', {}).get('id')
    else:
        print(f"❌ Failed to upload dataset (Status {response.status_code}):", response.text)
        return None


def test_upload_script():
    print("\n--- 4. Uploading Script ---")
    # Create a temporary dummy python file
    filename = "dummy_script.py"
    with open(filename, "w") as f:
        f.write("print('Hello from Spark!')")

    with open(filename, "rb") as f:
        # 'script' matches the request.FILES.get('script') in views.py
        files = {'script': (filename, f, 'text/x-python')}
        data = {'access_level': 'private'}
        response = session.post(f"{base_url}/scripts/upload/", files=files, data=data)

    os.remove(filename)  # Clean up the dummy file

    if response.status_code in [200, 201]:
        res_data = response.json()
        print("✅ Success:", res_data)
        return res_data.get('script_id')
    else:
        print(f"❌ Failed to upload script (Status {response.status_code}):", response.text)
        return None


def test_run_experiment(script_id, dataset_id):
    print("\n--- 5. Running Experiment ---")
    payload = {"dataset_id": dataset_id}

    # Note: URL pattern uses the script ID
    response = session.post(f"{base_url}/experiments/{script_id}/run_script/", json=payload)

    if response.status_code in [200, 201]:
        print("✅ Success:", response.json())
    else:
        print(f"❌ Failed to run experiment (Status {response.status_code}):", response.text)


if __name__ == "__main__":
    # Execute the full pipeline
    test_signup()
    test_login()

    dataset_id = test_upload_dataset()
    script_id = test_upload_script()

    if dataset_id and script_id:
        test_run_experiment(script_id, dataset_id)
    else:
        print("\n⚠️ Skipping experiment execution due to missing dataset or script IDs.")

    print("\nDone!")
