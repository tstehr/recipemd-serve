import os
import sys
from decimal import Decimal
from pprint import pprint
from typing import List

import commonmark
from flask import Flask, send_from_directory, request, render_template, redirect, abort
from lxml.html import document_fromstring, tostring
from lxml.html.clean import Cleaner
from markupsafe import Markup

from recipemd.data import Ingredient, RecipeParser, RecipeSerializer, get_recipe_with_yield, Amount


def serve(base_folder_path) -> Flask:
    app = Flask(__name__)

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

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

    @app.template_filter()
    def serialize_ingredients(ingredients: List[Ingredient]):
        return ("\n".join(recipe_serializer._serialize_ingredient(i, rounding=2) for i in ingredients)).strip()

    def forward_shortlink(shortlink: str):
        shortlink = shortlink.lower()
        all_files: List[str] = []
        for root, dirs, files in os.walk(base_folder_path):
            files = [f for f in files if not f[0] == '.']
            dirs[:] = [d for d in dirs if not d[0] == '.']
            rel_root = os.path.relpath(root, base_folder_path)
            all_files.extend(os.path.join(rel_root, file) for file in files)
            all_files.extend(os.path.join(rel_root, dir) for dir in dirs)
        print(all_files)
        files = [file for file in all_files if shortlink in file.lower()]
        if not files:
            abort(404)
        files.sort(key=lambda f: len(f))
        print(files)
        return redirect(f'/{files[0]}', code=302)

    def render_folder(relative_path: str, absolute_path: str): 
        if not absolute_path.endswith('/'):
            return redirect(f'/{relative_path}/', code=302)
        
        children = [ch for ch in os.listdir(absolute_path) if not ch.startswith('.')]
        # children = sorted(children, key=lambda ch: ch.casefold())

        child_folders, child_recipes, child_files = [], [], []
        for ch in children:
            absolute_child_path = os.path.join(absolute_path, ch)
            if os.path.isdir(absolute_child_path):
                ch = ch if ch.endswith('/') else f'{ch}/'
                child_folders.append(ch)
            else:
                try:
                    with open(absolute_child_path, 'r', encoding='UTF-8') as f:
                        recipe = recipe_parser.parse(f.read())
                    # TODO markdown to html
                    child_recipes.append((ch, recipe.title))
                except:
                    child_files.append(ch)

        child_folders = sorted(child_folders, key=lambda ch: ch.casefold())        
        child_recipes = sorted(child_recipes, key=lambda ch: ch[1].casefold())


        return render_template("folder.html", child_folders=child_folders, child_recipes=child_recipes, child_files=child_files, path=relative_path)

    def render_recipe(relative_path: str, absolute_path: str): 
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
            except Exception as e:
                errors.append(str(e))

            return render_template(
                "recipe.html",
                recipe=recipe,
                yields=recipe_serializer._serialize_yields(recipe.yields, rounding=2),
                tags=recipe_serializer._serialize_tags(recipe.tags),
                units=list(set(y.unit for y in recipe.yields)),
                default_yield=recipe_serializer._serialize_amount(recipe.yields[0]) if recipe.yields else "1",
                path=relative_path,
                errors=errors
            )

    @app.route('/')
    @app.route('/<path:relative_path>')
    def download_file(relative_path=''):
        absolute_path = os.path.join(base_folder_path, relative_path)

        if not os.path.exists(absolute_path): 
            return forward_shortlink(relative_path)

        if os.path.isdir(absolute_path):
            return render_folder(relative_path, absolute_path)

        if not absolute_path.endswith('.md'):
            return send_from_directory(base_folder_path, relative_path)

        return render_recipe(relative_path, absolute_path)

    return app




def main():
    if len(sys.argv) > 1:
        path = os.path.join(os.getcwd(), sys.argv[1])
    else: 
        path = os.getcwd()
    print(path)
    app = serve(path)
    app.run(host="0.0.0.0", debug=True)


if __name__ == "__main__":
    main()
