import json
import os
from pprint import pprint

import commonmark
from flask import Flask, send_from_directory, request, render_template, redirect
from lxml.html.clean import Cleaner
from markupsafe import Markup

from recipemd.data import RecipeParser, RecipeSerializer, get_recipe_with_yield


def serve(base_folder) -> Flask:
    app = Flask(__name__)

    recipe_parser = RecipeParser()
    recipe_serializer = RecipeSerializer()

    _cleaner = Cleaner(
        page_structure=True,
        meta=True,
        embedded=True,
        links=True,
        style=True,
        processing_instructions=True,
        scripts=True,
        javascript=True,
        frames=True,
        remove_unknown_tags=True,
    )

    @app.template_filter()
    def markdown_to_cleaned_html(markdown):
        unsafe_html = commonmark.commonmark(markdown)
        return Markup(_cleaner.clean_html(unsafe_html))

    @app.route('/')
    @app.route('/<path:filename>')
    def download_file(filename=''):
        path = os.path.join(base_folder, filename)
        pprint(path)

        if os.path.isdir(path):
            if not path.endswith('/'):
                return redirect(f'/{filename}/', code=302)

            child_paths = [(ch, os.path.isdir(os.path.join(path, ch))) for ch in os.listdir(path)]
            child_paths = [(ch, is_dir) for ch, is_dir in child_paths if not ch.startswith('.') and (is_dir or ch.endswith('.md'))]
            child_paths = [f'{ch}/' if not ch.endswith('/') and is_dir else ch for ch, is_dir in child_paths]
            child_paths = sorted(child_paths)
            return render_template("folder.html", child_paths=child_paths, path=filename)

        if not path.endswith('.md'):
            return send_from_directory(base_folder, filename)

        with open(path, 'r', encoding='UTF-8') as f:
            required_yield_str = request.args.get('yield', '1')
            required_yield = recipe_parser.parse_amount(required_yield_str)

            src = f.read()

            try:
                recipe = recipe_parser.parse(src)
            except Exception as e:
                return render_template("markdown.html", markdown=src, path=filename, errors=[e.args[0]])

            errors = []
            try:
                recipe = get_recipe_with_yield(recipe, required_yield)
            except StopIteration:
                errors.append(f'The recipe does not specify a yield in the unit "{required_yield.unit}". '
                              f'The following units can be used: ' + ", ".join(f'"{y.unit}"' for y in recipe.yields))

            recipe_markdown = recipe_serializer.serialize(recipe)
            units = list(set(y.unit for y in recipe.yields))

            return render_template("recipe.html", recipe_markdown=recipe_markdown, recipe=recipe, path=filename,
                                   units=units, errors=errors)


    return app




def main():
    app = serve(os.getcwd())
    app.run(host="0.0.0.0", debug=True)


if __name__ == "__main__":
    main()
