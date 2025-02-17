from graphql import (
    GraphQLField,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLType,
    GraphQLUnionType,
    is_wrapping_type,
)
from turms.errors import GenerationError
from turms.plugins.base import Plugin, PluginConfig
import ast
from typing import Dict, List
from turms.config import GeneratorConfig
from graphql.utilities.build_client_schema import GraphQLSchema
from pydantic import Field
from graphql.type.definition import (
    GraphQLEnumType,
)
from turms.registry import ClassRegistry
from turms.utils import (
    get_additional_bases_for_type,
    interface_is_extended_by_other_interfaces,
)


class ObjectsPluginConfig(PluginConfig):
    type = "turms.plugins.objects.ObjectsPlugin"
    types_bases: List[str] = ["pydantic.BaseModel"]
    skip_underscore: bool = False
    skip_double_underscore: bool = True

    class Config:
        env_prefix = "TURMS_PLUGINS_OBJECTS_"


def generate_object_field_annotation(
    graphql_type: GraphQLType,
    parent: str,
    config: GeneratorConfig,
    plugin_config: ObjectsPluginConfig,
    registry: ClassRegistry,
    is_optional=True,
):
    if isinstance(graphql_type, GraphQLScalarType):
        if is_optional:
            registry.register_import("typing.Optional")
            return ast.Subscript(
                value=ast.Name("Optional", ctx=ast.Load()),
                slice=registry.reference_scalar(graphql_type.name),
                ctx=ast.Load(),
            )

        return registry.reference_scalar(graphql_type.name)

    if isinstance(graphql_type, GraphQLInterfaceType):
        if is_optional:
            registry.register_import("typing.Optional")
            return ast.Subscript(
                value=ast.Name("Optional", ctx=ast.Load()),
                slice=registry.reference_interface(graphql_type.name, parent),
                ctx=ast.Load(),
            )

        return registry.reference_interface(graphql_type.name, parent)

    if isinstance(graphql_type, GraphQLObjectType):
        if is_optional:
            registry.register_import("typing.Optional")
            return ast.Subscript(
                value=ast.Name("Optional", ctx=ast.Load()),
                slice=registry.reference_object(graphql_type.name, parent),
                ctx=ast.Load(),
            )
        return registry.reference_object(graphql_type.name, parent)

    if isinstance(graphql_type, GraphQLUnionType):
        if is_optional:
            registry.register_import("typing.Optional")
            registry.register_import("typing.Union")
            return ast.Subscript(
                value=ast.Name("Optional", ctx=ast.Load()),
                slice=ast.Subscript(
                    value=ast.Name("Union", ctx=ast.Load()),
                    slice=ast.Tuple(
                        elts=[
                            generate_object_field_annotation(
                                union_type,
                                parent,
                                config,
                                plugin_config,
                                registry,
                                is_optional=False,
                            )
                            for union_type in graphql_type.types
                        ],
                        ctx=ast.Load(),
                    ),
                ),
                ctx=ast.Load(),
            )
        registry.register_import("typing.Union")

        return ast.Subscript(
            value=ast.Name("Union", ctx=ast.Load()),
            slice=ast.Tuple(
                elts=[
                    generate_object_field_annotation(
                        union_type,
                        parent,
                        config,
                        plugin_config,
                        registry,
                        is_optional=False,
                    )
                    for union_type in graphql_type.types
                ],
                ctx=ast.Load(),
            ),
            ctx=ast.Load(),
        )

    if isinstance(graphql_type, GraphQLEnumType):
        if is_optional:
            registry.register_import("typing.Optional")
            return ast.Subscript(
                value=ast.Name("Optional", ctx=ast.Load()),
                slice=registry.reference_enum(
                    graphql_type.name,
                    parent,
                    allow_forward=not config.force_plugin_order,
                ),
                ctx=ast.Load(),
            )
        return registry.reference_enum(
            graphql_type.name, parent, allow_forward=not config.force_plugin_order
        )

    if isinstance(graphql_type, GraphQLNonNull):
        return generate_object_field_annotation(
            graphql_type.of_type,
            parent,
            config,
            plugin_config,
            registry,
            is_optional=False,
        )

    if isinstance(graphql_type, GraphQLList):
        if is_optional:
            registry.register_import("typing.Optional")
            registry.register_import("typing.List")
            return ast.Subscript(
                value=ast.Name("Optional", ctx=ast.Load()),
                slice=ast.Subscript(
                    value=ast.Name("List", ctx=ast.Load()),
                    slice=generate_object_field_annotation(
                        graphql_type.of_type,
                        parent,
                        config,
                        plugin_config,
                        registry,
                        is_optional=True,
                    ),
                    ctx=ast.Load(),
                ),
                ctx=ast.Load(),
            )

        registry.register_import("typing.List")
        return ast.Subscript(
            value=ast.Name("List", ctx=ast.Load()),
            slice=generate_object_field_annotation(
                graphql_type.of_type,
                parent,
                config,
                plugin_config,
                registry,
                is_optional=True,
            ),
            ctx=ast.Load(),
        )

    raise NotImplementedError(f"Unknown input type {repr(graphql_type)}")


def generate_types(
    client_schema: GraphQLSchema,
    config: GeneratorConfig,
    plugin_config: ObjectsPluginConfig,
    registry: ClassRegistry,
):

    tree = []

    objects = {
        key: value
        for key, value in client_schema.type_map.items()
        if isinstance(value, GraphQLObjectType)
        and not isinstance(value, GraphQLInputObjectType)
        or isinstance(value, GraphQLInterfaceType)
    }

    sorted_objects = {
        k: v
        for k, v in sorted(
            objects.items(),
            key=lambda item: isinstance(item[1], GraphQLInterfaceType),
            reverse=True,
        )
    }

    interface_map: Dict[
        str, List[str]
    ] = {}  # A list of interfaces with the union classes attached
    interface_base_map: Dict[
        str, str
    ] = {}  # A list of interfaces with its respective base

    for base in plugin_config.types_bases:
        registry.register_import(base)

    for key, object_type in sorted_objects.items():

        additional_bases = get_additional_bases_for_type(
            object_type.name, config, registry
        )

        if plugin_config.skip_underscore and key.startswith("_"):
            continue

        if plugin_config.skip_double_underscore and key.startswith("__"):
            continue

        if isinstance(object_type, GraphQLObjectType):
            classname = registry.generate_objecttype(key)
        if isinstance(object_type, GraphQLInterfaceType):
            classname = registry.generate_interface(key)
            interface_base_map[key] = classname

        for interface in object_type.interfaces:
            # Populate the Union_classed
            interface_map.setdefault(interface.name, []).append(classname)

            other_interfaces = set(object_type.interfaces) - {interface}
            if not interface_is_extended_by_other_interfaces(
                interface, other_interfaces
            ):
                additional_bases.append(
                    ast.Name(
                        id=registry.inherit_interface(interface.name),
                        ctx=ast.Load(),
                    )
                )

        fields = (
            [ast.Expr(value=ast.Constant(value=object_type.description))]
            if object_type.description
            else []
        )

        for value_key, value in object_type.fields.items():
            value: GraphQLField
            field_name = registry.generate_node_name(value_key)

            if field_name != value_key:
                registry.register_import("pydantic.Field")
                assign = ast.AnnAssign(
                    target=ast.Name(field_name, ctx=ast.Store()),
                    annotation=generate_object_field_annotation(
                        value.type,
                        classname,
                        config,
                        plugin_config,
                        registry,
                        is_optional=True,
                    ),
                    value=ast.Call(
                        func=ast.Name(id="Field", ctx=ast.Load()),
                        args=[],
                        keywords=[
                            ast.keyword(
                                arg="alias", value=ast.Constant(value=value_key)
                            )
                        ],
                    ),
                    simple=1,
                )
            else:
                assign = ast.AnnAssign(
                    target=ast.Name(value_key, ctx=ast.Store()),
                    annotation=generate_object_field_annotation(
                        value.type,
                        classname,
                        config,
                        plugin_config,
                        registry,
                        is_optional=True,
                    ),
                    simple=1,
                )

            potential_comment = (
                value.description
                if not value.deprecation_reason
                else f"DEPRECATED: {value.description}"
            )

            if potential_comment:
                fields += [
                    assign,
                    ast.Expr(value=ast.Constant(value=potential_comment)),
                ]

            else:
                fields += [assign]

        tree.append(
            ast.ClassDef(
                classname,
                bases=additional_bases
                + [
                    ast.Name(id=base.split(".")[-1], ctx=ast.Load())
                    for base in plugin_config.types_bases
                ],
                decorator_list=[],
                keywords=[],
                body=fields,
            )
        )

    for interface, union_class_names in sorted(interface_map.items()):
        registry.register_import("typing.Union")
        tree.append(
            ast.Assign(
                targets=[ast.Name(id=interface, ctx=ast.Store())],
                value=ast.Subscript(
                    value=ast.Name("Union", ctx=ast.Load()),
                    slice=ast.Tuple(
                        elts=[
                            ast.Name(id=clsname, ctx=ast.Load())
                            for clsname in sorted(union_class_names)
                        ],
                        ctx=ast.Load(),
                    ),
                    ctx=ast.Load(),
                ),
            )
        )

    unimplemented_interfaces = {
        interface: baseclass
        for interface, baseclass in interface_base_map.items()
        if interface not in interface_map
    }
    if unimplemented_interfaces:
        if config.always_resolve_interfaces:
            raise GenerationError(
                f"Interfaces {unimplemented_interfaces.keys()} have no types implementing it. And we have set always_resolve_interfaces to true. Make sure your schema is correct"
            )

        for interface, baseclass in sorted(unimplemented_interfaces.items()):
            registry.warn(f"Interface {interface} has no types implementing it")
            tree.append(
                ast.Assign(
                    targets=[ast.Name(id=interface, ctx=ast.Store())],
                    value=ast.Name(baseclass, ctx=ast.Load()),
                )
            )

    return tree


class ObjectsPlugin(Plugin):
    config: ObjectsPluginConfig = Field(default_factory=ObjectsPluginConfig)

    def generate_ast(
        self,
        client_schema: GraphQLSchema,
        config: GeneratorConfig,
        registry: ClassRegistry,
    ) -> List[ast.AST]:

        return generate_types(client_schema, config, self.config, registry)
