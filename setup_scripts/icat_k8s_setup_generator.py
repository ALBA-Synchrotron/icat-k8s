import os
import sys

from icat_k8s_setup_utils import get_arguments, register_db, create_jms_resource, get_properties, \
    deploy, get_setup_parameters

args: dict = get_arguments()
component: str = args["component"]

prop_name: str = "run.properties"
overwrite_files: list = [[prop_name, "WEB-INF/classes"]]
asadmin_commands: list = []

match component:
    case "authn.anon":
        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(deployment_order=80, files=overwrite_files)
    case "authn.db":
        prop_list: list = ["db.driver", "db.url", "db.username", "db.password"]
        setup_props: dict = get_setup_parameters("setup.properties", prop_list)
        db_commands: list = register_db(setup_props, "authn_db")
        asadmin_commands.extend(db_commands)

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(deployment_order=80, files=overwrite_files)
    case "authn.oidc":
        prop_list: list = ["wellKnownUrl", "tokenIssuer", "icatUserClaim"]
        run_props: dict = get_setup_parameters(prop_name, prop_list)

        try:
            icat_user_claim_exception: str = run_props["icatUserClaimException"]
        except KeyError:
            icat_user_claim_exception = ""

        try:
            mechanism: str = run_props["mechanism"]
        except KeyError:
            mechanism = ""

        try:
            icat_user_prepend_mechanism: str = run_props["icatUserPrependMechanism"]
        except KeyError:
            icat_user_prepend_mechanism = ""

        if icat_user_prepend_mechanism == "true":
            if mechanism == "":
                sys.exit("icatUserPrependMechanism is 'true' but no mechanism is defined in run.properties")

        if mechanism != "":
            if icat_user_prepend_mechanism != "true":
                if icat_user_claim_exception == "true":
                    print(
                        "Warning: the mechanism defined in run.properties is never used because icatUserPrependMechanism=false and icatUserClaimException=true")

        if os.path.exists("logback.xml"): overwrite_files.append(["logback.xml", "WEB-INF/classes"])

        deploy(deployment_order=80, files=overwrite_files)
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
                                                  "container", "port", "container"])
        db_commands: list = register_db(setup_props, "icat")
        asadmin_commands.extend(db_commands)

        icat_jms_topic: str = create_jms_resource("jakarta.jms.Topic", "jms/ICAT/Topic")
        asadmin_commands.append(icat_jms_topic)

        icat_jms_log: str = create_jms_resource("jakarta.jms.Topic", "jms/ICAT/log")
        asadmin_commands.append(icat_jms_log)

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
    f.write("\n")
