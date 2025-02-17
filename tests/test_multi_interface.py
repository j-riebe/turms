import ast

import pytest
from turms.config import GeneratorConfig
from turms.helpers import build_schema_from_glob
from turms.plugins.enums import EnumsPlugin
from turms.plugins.fragments import FragmentsPlugin
from turms.plugins.funcs import FuncsPlugin, FuncsPluginConfig, FunctionDefinition
from turms.plugins.inputs import InputsPlugin
from turms.plugins.operations import OperationsPlugin
from turms.run import generate_ast
from turms.stylers.capitalize import CapitalizeStyler
from turms.stylers.default import DefaultStyler
from turms.stylers.snake_case import SnakeCaseStyler

from .utils import build_relative_glob, unit_test_with


@pytest.fixture()
def multi_interface_schema():
    return build_schema_from_glob(
        build_relative_glob("/schemas/multi_interface.graphql")
    )


def test_multi_interface_funcs(multi_interface_schema):
    config = GeneratorConfig(
        documents=build_relative_glob("/documents/multi_interface/*/**.graphql"),
    )
    generated_ast = generate_ast(
        config,
        multi_interface_schema,
        stylers=[CapitalizeStyler(), SnakeCaseStyler()],
        plugins=[
            EnumsPlugin(),
            InputsPlugin(),
            FragmentsPlugin(),
            OperationsPlugin(),
            FuncsPlugin(
                config=FuncsPluginConfig(
                    definitions=[
                        FunctionDefinition(
                            type="query",
                            use="tests.mocks.query",
                            is_async=False,
                        ),
                        FunctionDefinition(
                            type="query",
                            use="tests.mocks.query",
                            is_async=True,
                        ),
                        FunctionDefinition(
                            type="mutation",
                            use="tests.mocks.aquery",
                            is_async=False,
                        ),
                        FunctionDefinition(
                            type="mutation",
                            use="tests.mocks.aquery",
                            is_async=True,
                        ),
                        FunctionDefinition(
                            type="subscription",
                            use="tests.mocks.subscribe",
                            is_async=False,
                        ),
                        FunctionDefinition(
                            type="subscription",
                            use="tests.mocks.asubscribe",
                            is_async=True,
                        ),
                    ]
                ),
            ),
        ],
    )

    unit_test_with(generated_ast, "")


def test_fragment_generation(multi_interface_schema):
    config = GeneratorConfig(
        documents=build_relative_glob("/documents/multi_interface/*/**.graphql")
    )

    generated_ast = generate_ast(
        config,
        multi_interface_schema,
        stylers=[DefaultStyler()],
        plugins=[InputsPlugin(), EnumsPlugin(), FragmentsPlugin()],
    )

    unit_test_with(
        generated_ast,
        "assert FlowNodeBaseReactiveNode(id='soinosins', position={'x': 3, 'y': 3}).id, 'Needs to be not nown'",
    )
