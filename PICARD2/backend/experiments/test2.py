import requests
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
base_url = os.environ.get('BACKEND_LOCAL_URL')
if not base_url:
    raise RuntimeError("BACKEND_LOCAL_URL must be set in backend/.env or the environment.")
base_url = base_url.rstrip('/')

# Use a Session object to persist cookies (like sessionid and csrftoken)
session = requests.Session()

# Define the user data to send
user_data = {
    "username": "testuser_api_new",
    "password": "testpassword123"
}


def test_signup_and_login():
    print("\n--- 1. Signing up & Logging in ---")
    # Attempt signup (it's okay if the user already exists)
    session.post(f"{base_url}/auth/signup/", json=user_data)

    # Log in
    response = session.post(f"{base_url}/auth/user_login/", json=user_data)

    if response.status_code == 200:
        print("✅ Authenticated successfully")
        if 'csrftoken' in session.cookies:
            session.headers.update({'X-CSRFToken': session.cookies['csrftoken']})
    else:
        print(f"❌ Failed login (Status {response.status_code}):", response.text)
        exit(1)


def test_upload_dataset():
    print("\n--- 2. Uploading Dataset ---")
    filename = "dummy_dataset.csv"
    with open(filename, "w") as f:
        f.write("col1,col2\n10,20\n30,40")

    with open(filename, "rb") as f:
        files = {'file': (filename, f, 'text/csv')}
        data = {'access_level': 'private'}
        response = session.post(f"{base_url}/datasets/upload/csv/", files=files, data=data)

    os.remove(filename)

    if response.status_code in [200, 201]:
        res_data = response.json()
        print("✅ Dataset uploaded:", res_data)
        return res_data.get('data', {}).get('id')
    else:
        print(f"❌ Failed to upload dataset (Status {response.status_code}):", response.text)
        return None


def test_upload_script():
    print("\n--- 3. Uploading Script ---")
    filename = "dummy_script.py"
    with open(filename, "w") as f:
        f.write("import sys\nprint('Hello from Spark!')\nprint(f'Received dataset path: {sys.argv[1]}')")

    with open(filename, "rb") as f:
        files = {'script': (filename, f, 'text/x-python')}
        data = {'access_level': 'private'}
        response = session.post(f"{base_url}/scripts/upload/", files=files, data=data)

    os.remove(filename)

    if response.status_code in [200, 201]:
        res_data = response.json()
        print("✅ Script uploaded:", res_data)
        return res_data.get('script_id')
    else:
        print(f"❌ Failed to upload script (Status {response.status_code}):", response.text)
        return None


def test_create_and_run_experiment(script_id, dataset_id):
    print("\n--- 4. Creating Experiment ---")
    payload = {"script_id": script_id, "dataset_id": dataset_id}

    # Use the create endpoint
    create_res = session.post(f"{base_url}/experiments/create/", json=payload)
    if create_res.status_code not in [200, 201]:
        print(f"❌ Failed to create experiment:", create_res.text)
        return None

    exp_data = create_res.json()
    exp_id = exp_data.get('experiment_id')
    print(f"✅ Experiment Created successfully (ID: {exp_id}, Status: {exp_data.get('status')})")

    print("\n--- 5. Queueing Experiment ---")
    # Queue the experiment using the run_experiment endpoint
    run_res = session.post(f"{base_url}/experiments/{exp_id}/run_experiment/")

    if run_res.status_code in [200, 201]:
        print("✅ Experiment Queued successfully:", run_res.json())
        return exp_id
    else:
        print(f"❌ Failed to queue experiment:", run_res.text)
        return None


def poll_experiment_until_complete(experiment_id):
    print("\n--- 6. Polling Experiment Status ---")
    while True:
        response = session.get(f"{base_url}/experiments/{experiment_id}/")

        if response.status_code == 200:
            data = response.json()
            status = data.get('status')
            print(f"⏳ Current Status: {status}")

            if status in ['Success', 'Failed']:
                print("\n✅ Execution Finished!")
                print("--- Execution Output ---")
                print(data.get('output'))
                break
        else:
            print(f"❌ Failed to get experiment status:", response.text)
            break

        time.sleep(2)  # Wait 2 seconds before polling again


if __name__ == "__main__":
    test_signup_and_login()

    dataset_id = test_upload_dataset()
    script_id = test_upload_script()

    if dataset_id and script_id:
        experiment_id = test_create_and_run_experiment(script_id, dataset_id)
        if experiment_id:
            poll_experiment_until_complete(experiment_id)
    else:
        print("\n⚠️ Skipping experiment execution due to missing dataset or script IDs.")