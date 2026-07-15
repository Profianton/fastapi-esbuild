from jinja2 import nodes
from jinja2.ext import Extension


class ContextChanger(Extension):
    tags = {"render"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno  # consume "render"

        # First argument: template name
        template_node = parser.parse_expression()

        # Optional second argument: context dict
        if parser.stream.skip_if("name:with"):
            context_node = parser.parse_expression()
        else:
            # default empty dict if not provided
            context_node = nodes.Dict(lineno=lineno)

        return nodes.CallBlock(
            self.call_method("_render_template", [template_node, context_node]),
            [],
            [],
            [],
        ).set_lineno(lineno)

    def _render_template(self, template_name, context, caller):
        # context is fully isolated
        tmpl = self.environment.get_template(template_name)
        return tmpl.render(context)
