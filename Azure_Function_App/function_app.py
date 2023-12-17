import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
import base64
import json
import logging
import os
import requests


# Create an instance of the azure.functions.FunctionApp class
app = func.FunctionApp()

# Define function to obtain the Spotify Web API access token using client credentials
def get_access_token(client_id, client_secret):
    # Prepare the credentials by encoding them request to the Spotify API for an access token
    client_creds = f"{client_id}:{client_secret}"
    client_creds_b64 = base64.b64encode(client_creds.encode())

    # Spotify API authorization requires a POST request. Here I set the URL the request will be sent to, required header parameters, and the required body parameters, respectively.
    token_url = "https://accounts.spotify.com/api/token"
    token_headers = {"Authorization": f"Basic {client_creds_b64.decode()}"}
    token_data = {"grant_type": "client_credentials" }

    # Here I trigger the HTTP POST Request, and assign the JSON data response to a variable
    req = requests.post(token_url, data=token_data, headers=token_headers)
    token_response_data = req.json()

    # Check for a successful response and return the access token
    if req.status_code == 200:
        access_token = token_response_data['access_token']
        expires_in = token_response_data['expires_in'] #seconds
        token_type = token_response_data['token_type']
    # Create, print, and log a dictionary for a successful response
        api_token_success = {
            "Status": req.status_code,
            "Token Type": token_type,
            "Expires In": expires_in,
            "Token Response Data": token_response_data
        }
        print(api_token_success)
        logging.info("API Token Success: %s", api_token_success)
        return access_token

    else:
     # Create a dictionary for error response information
        api_token_error = {
            "Error": req.status_code,
            "Token Response Data": token_response_data
        }
        print(api_token_error)
        logging.error("API Token Error: %s", api_token_error)
        return None
    
# Define Azure Blob Storage upload function
def upload_to_blob_storage(file_name, data):
    try:
        # Set Blob Storage account URL from Azure Function App > Configuration > Application Settings (env variables)
        account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")

        #Set default Azure identity to managed identity from Azure Function App > Identity > System assigned > Status: On
        #This Managed Identity is granted a Storage Blob Data Contributor role in Storage Account > Access control > Add role assignment
        default_credential = DefaultAzureCredential()
        
        # Set Azure Blob Storage container name from Azure Function App > Configuration > Application Settings (env variables)
        container_name = os.environ.get('AZURE_STORAGE_CONTAINER_NAME')
        
        # Configure Blob service client to use account url and default Azure credentials for authentication parameters as opposed to an explicit connection string
        blob_service_client = BlobServiceClient(account_url, credential=default_credential)

        # Upload the file to Blob storage
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name)
        blob_client.upload_blob(data, content_settings=ContentSettings(content_type='application/json'), overwrite=True)

        # Log the successful Blob upload
        print(f"Uploaded {file_name} to Azure Blob Storage.")
        logging.info(f"Uploaded {file_name} to Azure Blob Storage.")
    
    # Log the Blob upload failure
    except Exception as e:
        print(f"Error uploading {file_name} to Azure Blob Storage: {str(e)}")
        logging.error(f"Error uploading {file_name} to Azure Blob Storage: {str(e)}")

# Decorator to define a timer-triggered function
@app.schedule(
    schedule="0 */1 * * * *", #Cron expression set to run the instance of the azure.functions.FunctionApp class we defined as 'app'
    arg_name="myTimer",
    run_on_startup=True,
    use_monitor=False
) 
def cron_trigger(myTimer: func.TimerRequest) -> None:
    # Set Spotify client values from Azure Function App > Configuration > Application Settings (env variables)
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')

    # Obtain Spotify access token
    access_token = get_access_token(client_id, client_secret)

    # Make the Spotify API call and upload responses to Azure Blob Storage
    if access_token:
        make_spotify_api_call(access_token)

# Function to make Spotify API calls and upload responses to Azure Blob Storage.
def make_spotify_api_call(access_token):
    #This artist name is URL-encoded manually, but it could be done with urllib package
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    artist_name = 'Thee%20Vellords'
    api_endpoint_search = f'https://api.spotify.com/v1/search?q={artist_name}&type=artist'
    response_search = requests.get(api_endpoint_search, headers=headers)
    search_data = response_search.json()

    if 'artists' in search_data and 'items' in search_data['artists'] and search_data['artists']['items']:
        first_result = search_data['artists']['items'][0]
        artist_id = first_result.get('id')
        print(f"Found artist with ID: {artist_id}")

        #Use the Artist Id to retrieve Artist data
        api_endpoint_artist = f'https://api.spotify.com/v1/artists/{artist_id}'
        response_artist = requests.get(api_endpoint_artist, headers=headers)
        artist_data = response_artist.json()
        print(artist_data)
        upload_to_blob_storage('artist_data.json', json.dumps(artist_data))
        
    else:
        print("No artists found in the response.")