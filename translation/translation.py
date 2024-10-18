import openai
import pandas as pd


def translate_text_with_openai(
    text,
    client,
    source_language_code,
    target_language_code,
    model_name,
    temperature,
) -> str:
    dict_languages = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
    }

    # Create the prompt
    prompt = f"""Translate the following article from {dict_languages[source_language_code]} to {dict_languages[target_language_code]}. Return only the translation, without any additional text or comments.\n
Original article:\n{text}
"""

    # Call the OpenAI API
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a bilingual translator."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4000,
        temperature=temperature,
    )

    return response.choices[0].message.content.strip()


def translate_csv_column(
    df,
    column_names,
    client,
    source_language_code,
    target_language_code,
    model_name,
    temperature,
) -> pd.DataFrame:
    for column_name in column_names:
        df[column_name + "_" + target_language_code] = df[column_name].apply(
            lambda x: translate_text_with_openai(
                x,
                client,
                source_language_code,
                target_language_code,
                model_name,
                temperature,
            )
        )
    return df
