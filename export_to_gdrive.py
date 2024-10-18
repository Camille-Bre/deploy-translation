import os.path
import urllib.parse

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes pour accéder à Google Docs et Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


# Fonction pour s'authentifier sur Google API
def google_authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "google_credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds


# Fonction pour vérifier si le document existe déjà dans un dossier Google Drive
# Fonction pour vérifier si le document existe déjà dans un dossier Google Drive
def document_exists(service_drive, folder_id, document_title):
    # Échapper les caractères spéciaux dans le titre
    escaped_title = urllib.parse.quote(document_title)

    query = f"'{folder_id}' in parents and name = '{escaped_title}' and mimeType = 'application/vnd.google-apps.document'"

    results = service_drive.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        print(f"Le document '{document_title}' existe déjà dans le dossier.")
        return True
    return False


# Fonction pour créer un document Google Docs dans un dossier spécifique
def create_google_doc(service_docs, service_drive, folder_id, document_title, content):
    # Créer le document seulement s'il n'existe pas
    if not document_exists(service_drive, folder_id, document_title):
        document = {"title": document_title}
        doc = service_docs.documents().create(body=document).execute()
        document_id = doc["documentId"]

        # Déplacer le document dans le dossier spécifié
        file = service_drive.files().get(fileId=document_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents"))
        service_drive.files().update(
            fileId=document_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()

        # Ajouter le contenu au document
        requests = [
            {
                "insertText": {
                    "location": {
                        "index": 1,
                    },
                    "text": content,
                }
            }
        ]
        service_docs.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()
        print(f"Document '{document_title}' créé avec succès dans le dossier.")
    else:
        print(f"Document '{document_title}' non créé car il existe déjà.")


# Fonction principale pour lire le CSV et créer des documents Google Docs dans un dossier spécifique
def main(csv_file, folder_id, lang_code):
    # Lire le fichier CSV
    df = pd.read_csv(csv_file)

    # Authentification sur Google API
    creds = google_authenticate()
    service_docs = build("docs", "v1", credentials=creds)
    service_drive = build("drive", "v3", credentials=creds)

    # Boucler sur chaque ligne du DataFrame
    for index, row in df.iterrows():
        # Create document with original title and content
        doc_title = f"{row['id']}_{row['title']}"
        doc_content = row["content"]

        # Créer un document Google Docs dans le dossier spécifié
        create_google_doc(
            service_docs, service_drive, folder_id, doc_title, doc_content
        )

        # Create document with translated title and content
        doc_title_translated = f"{row['id']}_{row['title_' + lang_code]}"
        doc_content_translated = row["content_" + lang_code]

        # Créer un document Google Docs dans le dossier spécifié
        create_google_doc(
            service_docs,
            service_drive,
            folder_id,
            doc_title_translated,
            doc_content_translated,
        )


if __name__ == "__main__":
    csv_file = "./data/posts_translated_es_Maria_241016.csv"  # Remplacez par le chemin de votre fichier CSV
    folder_id = "1KpNvszabc4KuI0AXbaA-dKuDdSQFeYsW"  # Remplacez par l'ID du dossier Google Drive où vous voulez créer les documents
    lang_code = "es"  # Remplacez par le code de langue de votre fichier CSV

    main(csv_file, folder_id, lang_code)
