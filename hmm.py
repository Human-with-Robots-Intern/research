import json
import requests

API_URL = (
    "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
)
api_token = "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"
headers = {"Authorization": f"Bearer {api_token}"}


def query(payload):
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()


data = query(
    {
        "inputs": {
            "source_sentence": "Dish|0|0|0",
            "sentences": ["Vase|+01.56|+00.56|-02.50",
      "Vase|+01.99|+00.56|-02.49",
      "Pan|+00.72|+00.90|-02.42",
      "Cup|+00.37|+01.64|-02.58",
      "PepperShaker|+00.30|+00.90|-02.47",
      "Potato|-01.66|+00.93|-02.15",
      "Bread|-00.52|+01.17|-00.03",
      "CreditCard|-00.46|+01.10|+00.87",
      "Statue|+01.96|+00.18|-02.54",
      "Plate|+00.96|+01.65|-02.61",
      "DishSponge|-01.94|+00.75|-01.71",
      "Spatula|+00.38|+00.91|-02.33",
      "Knife|-01.70|+00.79|-00.22",
      "Bottle|+01.54|+00.89|-02.54",
      "Tomato|-00.39|+01.14|-00.81",
      "Kettle|+01.04|+00.90|-02.60",
      "Mug|-01.76|+00.90|-00.62",
      "WineBottle|-01.00|+01.65|-02.58",
      "Lettuce|-01.81|+00.97|-00.94",
      "Apple|-00.47|+01.15|+00.48",
      "Bowl|+00.27|+01.10|-00.75",
      "Spoon|+00.98|+00.77|-02.29",
      "Egg|-02.04|+00.81|+01.24",
      "Fork|+00.95|+00.77|-02.37",
      "PaperTowelRoll|-02.06|+01.01|-00.81",
      "SaltShaker|+00.35|+00.90|-02.57",
      "SoapBottle|-01.99|+00.90|-02.03",
      "Pot|-01.22|+00.90|-02.36",
      "ButterKnife|-00.41|+01.11|-00.46",
      "Book|+00.15|+01.10|+00.62"],
        }
    }
)
sorted_data = sorted(enumerate(data), key=lambda x: x[1], reverse=True)[0][0]
print(sorted_data)

## [0.605, 0.894]
