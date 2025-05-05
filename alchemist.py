# file: alchemist.py
# RENDER AND PUBLISH ACCESS PAGES AND ASSETS

import argparse
import logging
import mimetypes

from pathlib import Path

from decouple import config, Csv

import cascflow

cascflow.setup_logging('settings.ini')
logger = logging.getLogger('alchemist')


# ## validate
# # validate_connection()
# # validate filesystem items
# # validate archival objects

# ## execute
# # move files to batch directory
# # detect sequence indicators
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

def is_archival_object_valid_for_publication(archival_object: dict, overwrite: bool = False) -> bool:
    if not archival_object["publish"]:
        message = "‼️ ARCHIVAL OBJECT NOT PUBLISHED: [**{}**]({}/resolve/readonly?uri={})".format(
            archival_object["title"],
            config("ARCHIVESSPACE_STAFF_URL"),
            archival_object["uri"],
        )
        logger.error(message)
        return False
    elif archival_object["has_unpublished_ancestor"]:
        message = "‼️ ARCHIVAL OBJECT HAS UNPUBLISHED ANCESTOR: [**{}**]({}/resolve/readonly?uri={})".format(
            archival_object["title"],
            config("ARCHIVESSPACE_STAFF_URL"),
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
                config("ARCHIVESSPACE_STAFF_URL"),
                archival_object["uri"],
            )
            logger.error(message)
            return False
        elif digital_object_count == 1:
            if instance["digital_object"]["_resolved"].get(
                "file_versions"
            ) and not overwrite:
                message = "‼️ DIGITAL OBJECT ALREADY HAS FILE VERSIONS: [**{}**]({}/resolve/readonly?uri={})".format(
                    instance["digital_object"]["_resolved"]["title"],
                    config("ARCHIVESSPACE_STAFF_URL"),
                    instance["digital_object"]["ref"],
                )
                logger.error(message)
                return False
            elif instance["digital_object"]["_resolved"].get("file_versions"):
                message = "⚠️ EXISTING WEB ACCESS FILES WILL BE REPLACED AND DIGITAL OBJECT RECORDS WILL BE UPDATED: [**{}**]({}/resolve/readonly?uri={})".format(
                    instance["digital_object"]["_resolved"]["title"],
                    config("ARCHIVESSPACE_STAFF_URL"),
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


def is_publication_file_supported(entry: Path) -> bool:
    type, encoding = mimetypes.guess_type(entry)
    ## TODO set supported types in configuration
    if type and (type.startswith("image/") or type.endswith("/mp4")):
        return True
    else:
        return False


def validate_for_publication(validation_results: dict, overwrite: bool = False) -> None:
    source_path = Path(validation_results.get("source_path"))
    valid_archival_objects = []
    invalid_archival_objects = []
    nested_directories = validation_results.get("nested_directories", [])
    empty_directories = validation_results.get("empty_directories", [])
    file_count = validation_results.get("file_count", 0)
    unsupported_files = []
    ## iterate over the first level of entries in the source directory
    for entry in source_path.iterdir():
        ## validate the entry (file or directory)
        if (archival_object := cascflow.find_archival_object(entry.stem)):
            if is_archival_object_valid_for_publication(archival_object, overwrite):
                valid_archival_objects.append(entry.stem)
            else:
                invalid_archival_objects.append(entry.stem)
        if entry.is_file():
            ## check for file types that are unsupported in publication
            if not is_publication_file_supported(entry):
                unsupported_files.append(entry)
        ## ensure directories do not contain subdirectories
        if entry.is_dir():
            for child in entry.iterdir():
                if child.is_file():
                    ## check for file types that are unsupported in publication
                    if not is_publication_file_supported(entry):
                        unsupported_files.append(entry)
    ## messaging
    if valid_archival_objects:
        for valid_archival_object in valid_archival_objects:
            logger.info(f"🉑 {valid_archival_object}")
        logger.info(f"🗂 ARCHIVAL OBJECT COUNT: {len(valid_archival_objects)}")
        logger.info(f"📄 FILE COUNT: {file_count}")
    ## validation and messaging
    if file_count == 0:
        message = "❌ NO FILES FOUND"
        logger.error(message)
        raise FileNotFoundError(message)
    if invalid_archival_objects:
        message = "❌ INVALID ARCHIVAL OBJECTS FOUND"
        logger.error(message)
        for invalid_archival_object in invalid_archival_objects:
            logger.error(f"❌ {invalid_archival_object}")
        raise RuntimeError(message)
    if nested_directories:
        message = "❌ NESTED DIRECTORIES FOUND"
        logger.error(message)
        for nested_directory in nested_directories:
            logger.error(f"❌ {nested_directory}")
        raise RuntimeError(message)
    if empty_directories:
        message = "❌ EMPTY DIRECTORIES FOUND"
        logger.error(message)
        for empty_directory in empty_directories:
            logger.error(f"❌ {empty_directory}")
        raise RuntimeError(message)
    if unsupported_files:
        message = "❌ UNSUPPORTED FILE TYPES FOUND"
        logger.error(message)
        for unsupported_file in unsupported_files:
            logger.error(f"❌ {unsupported_file}")
        raise RuntimeError(message)


def main():
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
        "--source-volume", required=True, help="String. Name of source volume."
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
        validation_results = cascflow.validate(args.source_volume)
        validate_for_publication(validation_results, overwrite=args.overwrite)
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
