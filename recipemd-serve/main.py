import os
from decimal import Decimal
from pprint import pprint

import commonmark
from flask import Flask, send_from_directory, request, render_template, redirect
from lxml.html import document_fromstring, tostring
from lxml.html.clean import Cleaner
from markupsafe import Markup

from recipemd.data import RecipeParser, RecipeSerializer, get_recipe_with_yield, Amount


def serve(base_folder_path) -> Flask:
    app = Flask(__name__)

    recipe_parser = RecipeParser()
    recipe_serializer = RecipeSerializer()

    _cleaner = Cleaner(
        meta=True,
        embedded=True,
        links=True,
        style=True,
        processing_instructions=True,
        scripts=True,
        javascript=True,
        frames=True,
        remove_unknown_tags=True,
        page_structure=True,
        remove_tags=['body']
    )

    @app.context_processor
    def pjax_processor():
        def get_root_template():
            if "X-PJAX" in request.headers:
                return "pjax.html"
            return "structure.html"

        return dict(get_root_template=get_root_template)

    @app.template_filter()
    def markdown_to_cleaned_html(markdown):
        unsafe_html_str = commonmark.commonmark(markdown)
        # remove wrapping div
        # https://stackoverflow.com/questions/21420922/how-to-use-cleaner-lxml-html-without-returning-div-tag
        unsafe_doc = document_fromstring(unsafe_html_str)
        clean_doc = _cleaner.clean_html(unsafe_doc)
        clean_html_str = "\n".join(tostring(ch, encoding="unicode") for ch in clean_doc)
        return Markup(clean_html_str)

    @app.template_filter()
    def get_recipe_title(child_name: str, parent_path) -> str:
        absolute_path = os.path.join(base_folder_path, parent_path, child_name)
        if os.path.isdir(absolute_path):
            return Markup('<em>Folder</em>')
        try:
            with open(absolute_path, 'r', encoding='UTF-8') as f:
                recipe = recipe_parser.parse(f.read())
            # TODO markdown to html
            return recipe.title
        except RuntimeError:
            return Markup('<strong>Invalid recipe!</strong>')

    @app.route('/')
    @app.route('/<path:relative_path>')
    def download_file(relative_path=''):
        absolute_path = os.path.join(base_folder_path, relative_path)

        if os.path.isdir(absolute_path):
            if not absolute_path.endswith('/'):
                return redirect(f'/{relative_path}/', code=302)

            child_paths = [(ch, os.path.isdir(os.path.join(absolute_path, ch))) for ch in os.listdir(absolute_path)]
            child_paths = [(ch, is_dir) for ch, is_dir in child_paths if not ch.startswith('.') and (is_dir or ch.endswith('.md'))]
            child_paths = [f'{ch}/' if not ch.endswith('/') and is_dir else ch for ch, is_dir in child_paths]
            child_paths = sorted(child_paths)
            return render_template("folder.html", child_paths=child_paths, path=relative_path)

        if not absolute_path.endswith('.md'):
            return send_from_directory(base_folder_path, relative_path)

        with open(absolute_path, 'r', encoding='UTF-8') as f:
            required_yield_str = request.args.get('yield', '1')
            required_yield = recipe_parser.parse_amount(required_yield_str)
            if required_yield is None:
                required_yield = Amount(factor=Decimal(1))

            src = f.read()

            try:
                recipe = recipe_parser.parse(src)
            except Exception as e:
                return render_template("markdown.html", markdown=src, path=relative_path, errors=[e.args[0]])

            errors = []
            try:
                recipe = get_recipe_with_yield(recipe, required_yield)
            except StopIteration:
                errors.append(f'The recipe does not specify a yield in the unit "{required_yield.unit}". '
                              f'The following units can be used: ' + ", ".join(f'"{y.unit}"' for y in recipe.yields))

            recipe_markdown = recipe_serializer.serialize(recipe)
            units = list(set(y.unit for y in recipe.yields))

            return render_template("recipe.html", recipe_markdown=recipe_markdown, recipe=recipe, path=relative_path,
                                   units=units, errors=errors)

    return app




def main():
    app = serve(os.getcwd())
    app.run(host="0.0.0.0", debug=True)


if __name__ == "__main__":
    main()
