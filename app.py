import os
from datetime import datetime

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, session, url_for
from openai import OpenAI

from translation.google_apis import google_authenticate, save_df_to_gdrive
from translation.translation import translate_csv_column

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Chemin des fichiers CSV
CSV_FILE = "./data/translation_followup_test.csv"
USERS_FILE = "./data/users.csv"
CONTENT_FILE = "./data/posts.csv"

# Initialize the OpenAI API
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


# Fonction pour charger les articles
def load_articles():
    return pd.read_csv(CSV_FILE)


# Fonction pour sauvegarder les articles
def save_articles(df):
    df.to_csv(CSV_FILE, index=False)


# Fonction pour charger les utilisateurs
def load_users():
    users_df = pd.read_csv(USERS_FILE)
    users_df["lang"] = users_df["lang"].fillna(
        "en"
    )  # Mettre 'en' par défaut si la langue est vide
    return users_df


# Page de connexion
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]

        # Charger les utilisateurs
        users_df = load_users()

        # Vérifier si l'utilisateur existe
        user = users_df[(users_df["username"] == username)]

        if not user.empty:
            session["username"] = username
            session["role"] = user.iloc[0]["role"]
            session["lang"] = user.iloc[0]["lang"]

            # Rediriger vers la page de sélection de langue si l'utilisateur est traducteur
            if session["role"] == "translator":
                return redirect(url_for("select_language"))

            # Rediriger vers le tableau de bord si l'utilisateur a un autre rôle
            return redirect(url_for("translator_dashboard"))

        flash("Nom d’utilisateur incorrect")
        return render_template("login.html")

    return render_template("login.html")


@app.route("/select_language", methods=["GET", "POST"])
def select_language():
    if request.method == "POST":
        lang = request.form["language"]
        session["lang"] = lang  # Enregistrer la langue choisie dans la session
        return redirect(url_for("translator_dashboard"))

    return render_template("select_language.html")


@app.route("/translator_dashboard", methods=["GET", "POST"])
def translator_dashboard():
    # Vérifier que l'utilisateur est connecté et a le rôle de traducteur
    if "username" not in session or session["role"] != "translator":
        return redirect(url_for("login"))

    # Charger les articles depuis le fichier CSV
    articles_df = load_articles()

    # Filtrer les articles en fonction de la langue choisie
    lang = session.get("lang")
    print(lang)
    ai_translated_column = "ai_translated_" + lang
    to_translate_column = "to_be_translated_" + lang

    # Sélectionner les articles qui n'ont pas encore été traduits et qui doivent être traduits
    articles_to_translate = articles_df[
        (articles_df[ai_translated_column] == False)
        & (articles_df[to_translate_column] == True)
    ]

    # Ordonner les articles par ID
    articles_to_translate = articles_to_translate.sort_values(by="id")

    if request.method == "POST":
        selected_articles = request.form.getlist("articles")
        selected_articles = list(map(int, selected_articles))
        # Ici vous pouvez ajouter la logique pour traduire les articles sélectionnés
        # Récupérer les articles sélectionnés et retrouver les contenus dans le fichier CSV
        posts_df = pd.read_csv(CONTENT_FILE)
        selected_posts = posts_df[posts_df["id"].isin(selected_articles)]

        # Traduire les colonnes "title" et "content" du DataFrame
        source_language_code = "fr"
        target_language_code = lang
        model_name = "gpt-4o"

        df_translated = translate_csv_column(
            selected_posts,
            ["title", "content"],
            client,
            source_language_code,
            target_language_code,
            model_name,
            temperature=0,
        )

        # Sauvegarder les traductions dans un fichier CSV avec nom unique
        output_file = f"./data/posts_translated_{target_language_code}_{session['username']}_{datetime.now().strftime('%d%m%y_%H%M%S')}.csv"

        # Changer la colonne "to_translate" à False pour les articles traduits dans le fichier CSV
        articles_df.loc[
            articles_df["id"].isin(selected_articles), to_translate_column
        ] = False

        # Change the "ai_translated" column to True for the translated articles in the CSV file
        articles_df.loc[
            articles_df["id"].isin(selected_articles), ai_translated_column
        ] = True

        # Sauvegarder les traductions dans google docs
        try:
            creds = google_authenticate()
            save_df_to_gdrive(creds, df_translated, lang)

            flash("Traduction effectuée avec succès.", "success")

            # Sauvegarder le fichier CSV mis à jour
            save_articles(articles_df)

        except Exception as e:
            flash(f"Erreur lors de la traduction : {str(e)}", "danger")

        return redirect(url_for("translator_dashboard"))

    return render_template("translator_dashboard.html", articles=articles_to_translate)


# Tableau de bord : affichage de tous les articles
# Tableau de bord : affichage des articles filtrés en fonction du rôle et de la langue
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    df = load_articles()

    # Filtrer les articles selon le rôle et la langue de l'utilisateur
    role = session["role"]
    filtered_articles = None

    if role == "translator":
        if session["lang"] == "en":
            filtered_articles = df[
                df["ai_translated_en"] == False
            ]  # Articles pas encore traduits en anglais
        elif session["lang"] == "es":
            filtered_articles = df[
                df["ai_translated_es"] == False
            ]  # Articles pas encore traduits en espagnol

    elif role == "reviewer":
        if session["lang"] == "en":
            filtered_articles = df[
                df["translation_reviewed_en"] == False
            ]  # Articles pas encore révisés en anglais
        elif session["lang"] == "es":
            filtered_articles = df[
                df["translation_reviewed_es"] == False
            ]  # Articles pas encore révisés en espagnol

    elif role == "approver":
        if session["lang"] == "en":
            filtered_articles = df[
                df["approved_en"] == False
            ]  # Articles pas encore approuvés en anglais
        elif session["lang"] == "es":
            filtered_articles = df[
                df["approved_es"] == False
            ]  # Articles pas encore approuvés en espagnol

    # Si un formulaire POST a été soumis
    if request.method == "POST":
        selected_articles = request.form.getlist(
            "article_ids"
        )  # Obtenir les articles sélectionnés
        for article_id in selected_articles:
            article_id = int(article_id)

            # Effectuer l'action en fonction du rôle
            if role == "translator":
                if session["lang"] == "en":
                    df.loc[df["id"] == article_id, "ai_translated_en"] = True
                elif session["lang"] == "es":
                    df.loc[df["id"] == article_id, "ai_translated_es"] = True

            elif role == "reviewer":
                if session["lang"] == "en":
                    df.loc[df["id"] == article_id, "translation_reviewed_en"] = True
                    df.loc[df["id"] == article_id, "translation_reviewed_by_en"] = (
                        session["username"]
                    )
                elif session["lang"] == "es":
                    df.loc[df["id"] == article_id, "translation_reviewed_es"] = True
                    df.loc[df["id"] == article_id, "translation_reviewed_by_es"] = (
                        session["username"]
                    )

            elif role == "approver":
                if session["lang"] == "en":
                    df.loc[df["id"] == article_id, "approved_en"] = True
                    df.loc[df["id"] == article_id, "approved_by_en"] = session[
                        "username"
                    ]
                elif session["lang"] == "es":
                    df.loc[df["id"] == article_id, "approved_es"] = True
                    df.loc[df["id"] == article_id, "approved_by_es"] = session[
                        "username"
                    ]

        # Sauvegarder les changements dans le CSV
        save_articles(df)

        flash("Les articles sélectionnés ont été mis à jour.")
        return redirect(url_for("dashboard"))

    return render_template(
        "dashboard.html", articles=filtered_articles.to_dict(orient="records")
    )


# Détails d'un article spécifique
@app.route("/article/<int:article_id>", methods=["GET", "POST"])
def article(article_id):
    if "username" not in session:
        return redirect(url_for("login"))

    df = load_articles()
    article = df[df["id"] == article_id].iloc[0]

    if request.method == "POST":
        role = session["role"]
        username = session["username"]

        # Actions en fonction du rôle
        if role == "translator":
            if "translate_en" in request.form:
                df.loc[df["id"] == article_id, "ai_translated_en"] = True
            elif "translate_es" in request.form:
                df.loc[df["id"] == article_id, "ai_translated_es"] = True

        if role == "reviewer":
            if "review_en" in request.form:
                df.loc[df["id"] == article_id, "translation_reviewed_en"] = True
                df.loc[df["id"] == article_id, "translation_reviewed_by_en"] = username
            elif "review_es" in request.form:
                df.loc[df["id"] == article_id, "translation_reviewed_es"] = True
                df.loc[df["id"] == article_id, "translation_reviewed_by_es"] = username

        if role == "approver":
            if "approve_en" in request.form:
                df.loc[df["id"] == article_id, "approved_en"] = True
                df.loc[df["id"] == article_id, "approved_by_en"] = username
            elif "approve_es" in request.form:
                df.loc[df["id"] == article_id, "approved_es"] = True
                df.loc[df["id"] == article_id, "approved_by_es"] = username

        save_articles(df)
        return redirect(url_for("dashboard"))

    return render_template("article.html", article=article)


# Déconnexion
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
