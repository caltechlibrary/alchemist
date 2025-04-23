# file: alchemist.py
# RENDER AND PUBLISH ACCESS PAGES AND ASSETS

import argparse
import logging

from decouple import config

import cascflow

cascflow.setup_logging('settings.ini')
logger = logging.getLogger('alchemist')


# ## validate
# # validate_connection()
# # validate filesystem items
# # detect sequence indicators
# # validate archival objects

# ## execute
# # move files to batch directory
# # find_archival_object()
# # get_arrangement()
# # collection_structure_processing()
# # move to working directory
# # if accessDistiller:
# #     accessDistiller.archival_object_level_processing(self.variables)
# #     build_directory = accessDistiller.get_build_directory()
# #     self.access_platform.loop_over_archival_object_files(
# #         build_directory, self.variables
# #     )
# # if accessDistiller:
# #     # NOTE working on variables["archival_object"]["component_id"]
# #     accessDistiller.transfer_archival_object_derivative_files(
# #         self.variables
# #     )
# #     # NOTE this is where we create_digital_object_file_versions()
# #     accessDistiller.loop_over_derivative_structure(self.variables)
# # move to completed directory

def is_archival_object_valid_for_publication(archival_object, **kwargs):
    if not archival_object["publish"]:
        message = "‼️ ARCHIVAL OBJECT NOT PUBLISHED: [**{}**]({}/resolve/readonly?uri={})".format(
            archival_object["title"],
            config("ASPACE_STAFF_URL"),
            archival_object["uri"],
        )
        logger.error(message)
        return False
    elif archival_object["has_unpublished_ancestor"]:
        message = "‼️ ARCHIVAL OBJECT HAS UNPUBLISHED ANCESTOR: [**{}**]({}/resolve/readonly?uri={})".format(
            archival_object["title"],
            config("ASPACE_STAFF_URL"),
            archival_object["uri"],
        )
        logger.error(message)
        return False
    ## check for existing digital_object["file_versions"]
    elif archival_object.get("instances"):
        digital_object_count = 0
        for instance in archival_object["instances"]:
            if "digital_object" in instance.keys():
                digital_object_count += 1
        if digital_object_count > 1:
            message = "‼️ MULTIPLE DIGITAL OBJECTS FOUND: [**{}**]({}/resolve/readonly?uri={})".format(
                archival_object["title"],
                config("ASPACE_STAFF_URL"),
                archival_object["uri"],
            )
            logger.error(message)
            return False
        elif digital_object_count == 1:
            if instance["digital_object"]["_resolved"].get(
                "file_versions"
            ) and not kwargs.get("overwrite", False):
                message = "‼️ DIGITAL OBJECT ALREADY HAS FILE VERSIONS: [**{}**]({}/resolve/readonly?uri={})".format(
                    instance["digital_object"]["_resolved"]["title"],
                    config("ASPACE_STAFF_URL"),
                    instance["digital_object"]["ref"],
                )
                logger.error(message)
                return False
            elif instance["digital_object"]["_resolved"].get("file_versions"):
                message = "⚠️ EXISTING WEB ACCESS FILES WILL BE REPLACED AND DIGITAL OBJECT RECORDS WILL BE UPDATED: [**{}**]({}/resolve/readonly?uri={})".format(
                    instance["digital_object"]["_resolved"]["title"],
                    config("ASPACE_STAFF_URL"),
                    instance["digital_object"]["ref"],
                )
                logger.warning(message)
                return True
            else:
                ## no file versions exist yet
                return True
        else:
            ## go through with creating a new digital_object
            return True
    else:
        ## ensure there is a return value
        return True

cascflow.register_archival_object_valid_for_publication_checker(is_archival_object_valid_for_publication)

def main():
    print("Hello from alchemist!")
    parser = argparse.ArgumentParser(
        description="Publication workflow for Caltech Archives."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # subcommand: validate
    validate_parser = subparsers.add_parser(
        "validate", help="Validate connections, files, and data."
    )
    validate_parser.add_argument(
        "--source-volume", required=True, help="String. Name of source volume."
    )
    validate_parser.add_argument(
        "--overwrite", action="store_true", help="Boolean. Overwrite existing Digital Objects."
    )

    # subcommand: execute
    execute_parser = subparsers.add_parser("execute", help="Execute the publication process.")
    execute_parser.add_argument(
        "--destinations", required=True, help="JSON string of destinations."
    )
    execute_parser.add_argument(
        "--batch-set-id", required=True, help="Batch set ID for processing."
    )

    # subcommand: regenerate
    regenerate_parser = subparsers.add_parser(
        "regenerate", help="Regenerate files for a component, collection, or all items."
    )
    regenerate_parser.add_argument(
        "--component-id", help="Component ID for regeneration."
    )
    regenerate_parser.add_argument(
        "--collection-id", help="Collection ID for regeneration."
    )
    regenerate_parser.add_argument(
        "--logfile", required=True, help="Path to the logfile."
    )

    args = parser.parse_args()

    # handle the commands
    if args.command == "validate":
        cascflow.validate(args.source_volume, pipeline="publication", overwrite=args.overwrite)
    elif args.command == "execute":
        cascflow.execute(args.destinations, args.batch_set_id)
    # elif args.command == "regenerate":
    #     alchemist_regenerate(
    #         component_id=args.component_id,
    #         collection_id=args.collection_id,
    #         logfile=args.logfile,
    #     )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
