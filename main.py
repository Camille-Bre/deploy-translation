import os

import pandas as pd
from openai import OpenAI

from translation.database import get_posts_from_titles
from translation.translation import translate_csv_column

# Load the data
data = pd.read_csv("./data/articles_traduction_espagnol_241016.csv")

# Only keep the "A traduire ?" OUI
data = data[data["A traduire ?"] == "OUI"]
# Respo is Maria or Cintia
data = data[data["Respo"].isin(["Cintia"])]

# Select the first 10 articles
# data = data.head(10)

posts_df = get_posts_from_titles(data)

# Initialize the OpenAI API
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# Translate the content of the posts
source_language_code = "fr"
target_language_code = "es"
model_name = "gpt-4o"

df_translated = translate_csv_column(
    posts_df,
    ["title", "content"],
    client,
    source_language_code,
    target_language_code,
    model_name,
    temperature=0,
)

# Save the translated posts
df_translated.to_csv("./data/posts_translated_es_Cintia_241016.csv", index=False)
