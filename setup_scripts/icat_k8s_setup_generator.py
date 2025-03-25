import os
import sys

from icat_k8s_setup_utils import get_arguments, register_db, get_db_parameters, create_jms_resource, get_properties, \
    deploy, get_setup_parameters

args: dict = get_arguments()
component: str = args["component"]

prop_name: str = "run.properties"

asadmin_commands: list = []
match component:
    case "icat.server":
        prop_list: list = ["lifetimeMinutes", "rootUserNames", "authn.list", "notification.list", "log.list"]
        icat_properties: dict = get_properties(prop_name, prop_list)

        for v in icat_properties["authn.list"].split():
            if f"authn.{v}.jndi" not in icat_properties and f"authn.{v}.url" not in icat_properties:
                sys.exit(f"authn.list included {v} but neither authn.{v}.url nor authn.{v}.jndi is not defined")

        if icat_properties["notification.list"]:
            for v in icat_properties["notification.list"].split():
                if f"notification.{v}" not in icat_properties:
                    sys.exit(f"notification.list included {v} but notification.{v} is not defined")

        setup_props: dict = get_setup_parameters("setup.properties",
                                                 ["db.driver", "db.url", "db.username", "db.password", "secure", "home",
                                                  "container", "port", "container", "db.logging"])
        db_commands: list = register_db(setup_props, "icat")
        asadmin_commands.extend(db_commands)

        icat_jms_topic: str = create_jms_resource("jakarta.jms.Topic", "jms/ICAT/Topic")
        asadmin_commands.append(icat_jms_topic)

        icat_jms_log: str = create_jms_resource("jakarta.jms.Topic", "jms/ICAT/log")
        asadmin_commands.append(icat_jms_log)

        overwrite_files: list = [[prop_name, "WEB-INF/classes"]]
        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        secure: bool = setup_props.get("secure", "false") == "true"
        port: int = setup_props.get("port", 8080)

        deploy(deployment_order=100, files=overwrite_files,
               jms_topic_connection_factory=icat_properties.get("jms.topicConnectionFactory"),
               target=setup_props.get("db.target"), logging=setup_props.get("db.logging"), port=port, secure=secure)
    case _:
        print(f"Unknown component: {component}")
        exit(1)

with open("post_boot_asadmin_commands", "w") as f:
    f.write("\n".join(asadmin_commands))
