project = "eshet.py"
copyright = "2023, Thomas Nixon"
author = "Thomas Nixon"

extensions = []

extensions.append("sphinx.ext.autodoc")
autodoc_class_signature = "separated"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"

extensions.append("sphinx.ext.napoleon")

templates_path = ["_templates"]
exclude_patterns = []

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
