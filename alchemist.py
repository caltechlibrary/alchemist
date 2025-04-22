# file: alchemist.py
# RENDER AND PUBLISH ACCESS PAGES AND ASSETS

import argparse

import cascflow


# ## validate
# # validate_connection()
# # validate filesystem items
# # detect sequence indicators
# # validate archival objects

# ## run
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


def main():
    print("Hello from alchemist!")
    parser = argparse.ArgumentParser(
        description="Digital object publication workflow for Caltech Archives."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: validate
    validate_parser = subparsers.add_parser(
        "validate", help="Validate connections, files, and data."
    )
    validate_parser.add_argument(
        "--destinations", required=True, help="JSON string of destinations."
    )
    validate_parser.add_argument(
        "--batch-set-id", required=True, help="Batch set ID for validation."
    )

    # Subcommand: run
    run_parser = subparsers.add_parser("run", help="Run the distillery process.")
    run_parser.add_argument(
        "--destinations", required=True, help="JSON string of destinations."
    )
    run_parser.add_argument(
        "--batch-set-id", required=True, help="Batch set ID for processing."
    )

    # Subcommand: regenerate
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

    # Handle the commands
    if args.command == "validate":
        cascflow.validate(args.destinations, args.batch_set_id)
    # elif args.command == "run":
    #     run(args.destinations, args.batch_set_id)
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
