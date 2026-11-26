"""Choose one disclosed frontier model per world for the WorldFeed header."""

import json
import sys

from .model_era import classify_model_era, explicit_frontier


def primary_model(world):
    models = world["models_used"]
    for model in models:
        if explicit_frontier(model):
            return model
    for model in models:
        if classify_model_era([model], world["published_at"]) == "frontier":
            return model
    return None


if __name__ == "__main__":
    print(json.dumps([primary_model(world) for world in json.load(sys.stdin)]))
