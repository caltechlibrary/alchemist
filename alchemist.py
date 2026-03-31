# file: alchemist.py
# RENDER AND PUBLISH ACCESS PAGES AND ASSETS

import argparse
import datetime
import json
import logging
import mimetypes
import shutil
import subprocess
import tempfile
import time

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import boto3  # pypi: boto3
import jinja2  # pypi: Jinja2

from decouple import Config, RepositoryIni  # pypi: python-decouple-typed

import cascflow

parser = argparse.ArgumentParser(
    description="Publication workflow for Caltech Archives."
)
parser.add_argument(
    "--settings",
    default=None,
    help="Path to settings.ini file (optional). Defaults to working directory.",
)
subparsers = parser.add_subparsers(dest="command", required=True)

# subcommand: validate
validate_parser = subparsers.add_parser(
    "validate", help="Validate connections, files, and data."
)
validate_parser.add_argument(
    "--target",
    required=True,
    choices=["publication", "metadata", "files"],
    help="String. Target for validation. Limited choices.",
)
validate_parser.add_argument(
    "--context",
    required=True,
    help="String. Supply a volume name or an identifier, depending on the target.",
)

# subcommand: execute
execute_parser = subparsers.add_parser(
    "execute", help="Execute the publication process."
)
execute_parser.add_argument(
    "--target",
    required=True,
    choices=["publication", "metadata", "files"],
    help="String. Target for validation. Limited choices.",
)
execute_parser.add_argument(
    "--context",
    required=True,
    help="String. Supply a volume name or an identifier, depending on the target.",
)

args = None
config = cascflow.config
logger = logging.getLogger("alchemist")


LINKED_AGENT_ARCHIVAL_RECORD_RELATORS = {
    "abr": "Abridger",
    "acp": "Art copyist",
    "act": "Actor",
    "adi": "Art director",
    "adp": "Adapter",
    "aft": "Author of afterword, colophon, etc.",
    "anl": "Analyst",
    "anm": "Animator",
    "ann": "Annotator",
    "ant": "Bibliographic antecedent",
    "ape": "Appellee",
    "apl": "Appellant",
    "app": "Applicant",
    "aqt": "Author in quotations or text abstracts",
    "arc": "Architect",
    "ard": "Artistic director",
    "arr": "Arranger",
    "art": "Artist",
    "asg": "Assignee",
    "asn": "Associated name",
    "ato": "Autographer",
    "att": "Attributed name",
    "auc": "Auctioneer",
    "aud": "Author of dialog",
    "aui": "Author of introduction, etc.",
    "aus": "Author of screenplay, etc.",
    "aut": "Author",
    "bdd": "Binding designer",
    "bjd": "Bookjacket designer",
    "bkd": "Book designer",
    "bkp": "Book producer",
    "blw": "Blurb writer",
    "bnd": "Binder",
    "bpd": "Bookplate designer",
    "brd": "Broadcaster",
    "brl": "Braille embosser",
    "bsl": "Bookseller",
    "cas": "Caster",
    "ccp": "Conceptor",
    "chr": "Choreographer",
    "clb": "Collaborator",
    "cli": "Client",
    "cll": "Calligrapher",
    "clr": "Colorist",
    "clt": "Collotyper",
    "cmm": "Commentator",
    "cmp": "Composer",
    "cmt": "Compositor",
    "cnd": "Conductor",
    "cng": "Cinematographer",
    "cns": "Censor",
    "coe": "Contestant-appellee",
    "col": "Collector",
    "com": "Compiler",
    "con": "Conservator",
    "cor": "Collection registrar",
    "cos": "Contestant",
    "cot": "Contestant-appellant",
    "cou": "Court governed",
    "cov": "Cover designer",
    "cpc": "Copyright claimant",
    "cpe": "Complainant-appellee",
    "cph": "Copyright holder",
    "cpl": "Complainant",
    "cpt": "Complainant-appellant",
    "cre": "Creator",
    "crp": "Correspondent",
    "crr": "Corrector",
    "crt": "Court reporter",
    "csl": "Consultant",
    "csp": "Consultant to a project",
    "cst": "Costume designer",
    "ctb": "Contributor",
    "cte": "Contestee-appellee",
    "ctg": "Cartographer",
    "ctr": "Contractor",
    "cts": "Contestee",
    "ctt": "Contestee-appellant",
    "cur": "Curator of an exhibition",
    "cwt": "Commentator for written text",
    "dbp": "Distribution place",
    "dfd": "Defendant",
    "dfe": "Defendant-appellee",
    "dft": "Defendant-appellant",
    "dgg": "Degree grantor",
    "dgs": "Degree supervisor",
    "dis": "Dissertant",
    "dln": "Delineator",
    "dnc": "Dancer",
    "dnr": "Donor",
    "dpc": "Depicted",
    "dpt": "Depositor",
    "drm": "Draftsman",
    "drt": "Director",
    "dsr": "Designer",
    "dst": "Distributor",
    "dtc": "Data contributor",
    "dte": "Dedicatee",
    "dtm": "Data manager",
    "dto": "Dedicator",
    "dub": "Dubious author",
    "edc": "Editor of compilation",
    "edm": "Editor of moving image work",
    "edt": "Editor",
    "egr": "Engraver",
    "elg": "Electrician",
    "elt": "Electrotyper",
    "eng": "Engineer",
    "enj": "Enacting jurisdiction",
    "etr": "Etcher",
    "evp": "Event place",
    "exp": "Appraiser",
    "fac": "Facsimilist",
    "fds": "Film distributor",
    "fld": "Field director",
    "flm": "Film editor",
    "fmd": "Film director",
    "fmk": "Filmmaker",
    "fmo": "Former owner",
    "fmp": "Film producer",
    "fnd": "Funder",
    "fpy": "First party",
    "frg": "Forger",
    "gis": "Geographic information specialist",
    "grt": "Graphic technician",
    "his": "Host institution",
    "hnr": "Honoree",
    "hst": "Host",
    "ill": "Illustrator",
    "ilu": "Illuminator",
    "ins": "Inscriber",
    "inv": "Inventor",
    "isb": "Issuing body",
    "itr": "Instrumentalist",
    "ive": "Interviewee",
    "ivr": "Interviewer",
    "jud": "Judge",
    "jug": "Jurisdiction governed",
    "lbr": "Laboratory",
    "lbt": "Librettist",
    "ldr": "Laboratory director",
    "led": "Lead",
    "lee": "Libelee-appellee",
    "lel": "Libelee",
    "len": "Lender",
    "let": "Libelee-appellant",
    "lgd": "Lighting designer",
    "lie": "Libelant-appellee",
    "lil": "Libelant",
    "lit": "Libelant-appellant",
    "lsa": "Landscape architect",
    "lse": "Licensee",
    "lso": "Licensor",
    "ltg": "Lithographer",
    "lyr": "Lyricist",
    "mcp": "Music copyist",
    "mdc": "Metadata contact",
    "med": "Medium",
    "mfp": "Manufacture place",
    "mfr": "Manufacturer",
    "mod": "Moderator",
    "mon": "Monitor",
    "mrb": "Marbler",
    "mrk": "Markup editor",
    "msd": "Musical director",
    "mte": "Metal-engraver",
    "mtk": "Minute taker",
    "mus": "Musician",
    "nrt": "Narrator",
    "opn": "Opponent",
    "org": "Originator",
    "orm": "Organizer of meeting",
    "osp": "Onscreen presenter",
    "oth": "Other",
    "own": "Owner",
    "pan": "Panelist",
    "pat": "Patron",
    "pbd": "Publishing director",
    "pbl": "Publisher",
    "pdr": "Project director",
    "pfr": "Proofreader",
    "pht": "Photographer",
    "plt": "Platemaker",
    "pma": "Permitting agency",
    "pmn": "Production manager",
    "pop": "Printer of plates",
    "ppm": "Papermaker",
    "ppt": "Puppeteer",
    "pra": "Praeses",
    "prc": "Process contact",
    "prd": "Production personnel",
    "pre": "Presenter",
    "prf": "Performer",
    "prg": "Programmer",
    "prm": "Printmaker",
    "prn": "Production company",
    "pro": "Producer",
    "prp": "Production place",
    "prs": "Production designer",
    "prt": "Printer",
    "prv": "Provider",
    "pta": "Patent applicant",
    "pte": "Plaintiff-appellee",
    "ptf": "Plaintiff",
    "pth": "Patentee",
    "ptt": "Plaintiff-appellant",
    "pup": "Publication place",
    "rbr": "Rubricator",
    "rcd": "Recordist",
    "rce": "Recording engineer",
    "rcp": "Recipient",
    "rdd": "Radio director",
    "red": "Redaktor",
    "ren": "Renderer",
    "res": "Researcher",
    "rev": "Reviewer",
    "rpc": "Radio producer",
    "rps": "Repository",
    "rpt": "Reporter",
    "rpy": "Responsible party",
    "rse": "Respondent-appellee",
    "rsg": "Restager",
    "rsp": "Respondent",
    "rsr": "Restorationist",
    "rst": "Respondent-appellant",
    "rth": "Research team head",
    "rtm": "Research team member",
    "sad": "Scientific advisor",
    "sce": "Scenarist",
    "scl": "Sculptor",
    "scr": "Scribe",
    "sds": "Sound designer",
    "sec": "Secretary",
    "sgd": "Stage director",
    "sgn": "Signer",
    "sht": "Supporting host",
    "sll": "Seller",
    "sng": "Singer",
    "spk": "Speaker",
    "spn": "Sponsor",
    "spy": "Second party",
    "srv": "Surveyor",
    "std": "Set designer",
    "stg": "Setting",
    "stl": "Storyteller",
    "stm": "Stage manager",
    "stn": "Standards body",
    "str": "Stereotyper",
    "tcd": "Technical director",
    "tch": "Teacher",
    "ths": "Thesis advisor",
    "tld": "Television director",
    "tlp": "Television producer",
    "trc": "Transcriber",
    "trl": "Translator",
    "tyd": "Type designer",
    "tyg": "Typographer",
    "uvp": "University place",
    "vac": "Voice actor",
    "vdg": "Videographer",
    "voc": "Vocalist",
    "wac": "Writer of added commentary",
    "wal": "Writer of added lyrics",
    "wam": "Writer of accompanying material",
    "wat": "Writer of added text",
    "wdc": "Woodcutter",
    "wde": "Wood engraver",
    "win": "Writer of introduction",
    "wit": "Witness",
    "wpr": "Writer of preface",
    "wst": "Writer of supplementary textual content",
}

RIGHTS_NOTICE_HTML = '<p>These digitized collections are accessible for purposes of education and research. Due to the nature of archival collections, archivists at the Caltech Archives and Special Collections are not always able to identify copyright and rights of privacy, publicity, or trademark. We are eager to <a href="mailto:archives@caltech.edu">hear from any rights holders</a>, so that we may obtain accurate information. Upon request, we’ll remove material from public view while we address a rights issue.</p>'


def invalidate_cloudfront_paths(paths=None, caller_reference=None):
    if not caller_reference:
        caller_reference = str(time.time())
    cloudfront_client = boto3.client(
        "cloudfront",
        aws_access_key_id=config("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=config("AWS_SECRET_ACCESS_KEY"),
    )
    if paths is None:
        paths = ["/*"]
    quantity = len(paths)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudfront/client/create_invalidation.html
    response = cloudfront_client.create_invalidation(
        DistributionId=config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID"),
        InvalidationBatch={
            "Paths": {"Quantity": quantity, "Items": paths},
            "CallerReference": caller_reference,
        },
    )
    logger.debug(f"🐞 CLOUDFRONT INVALIDATION RESPONSE: {str(response)}")
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudfront/waiter/InvalidationCompleted.html
    waiter = cloudfront_client.get_waiter("invalidation_completed")
    logger.debug("🐞 WAITING ON CLOUDFRONT INVALIDATION")
    waiter.wait(
        DistributionId=config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID"),
        Id=response["Invalidation"]["Id"],
    )
    logger.debug("🐞 CLOUDFRONT INVALIDATION COMPLETE")


def create_canvas_metadata(
    filepath: Path, archival_object: dict, arrangement: dict, sequence_indicators: dict
) -> dict:
    magick_identify = subprocess.run(
        [
            config("MAGICK_CMD"),
            "identify",
            "-format",
            "%w*%h",
            filepath.as_posix(),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    dimensions = magick_identify.stdout.strip().split("*")
    canvas_id = "/".join(
        [
            config("ALCHEMIST_BASE_URL").rstrip("/"),
            config("COMMON_PATH_PREFIX"),
            arrangement["collection_id"],
            archival_object["component_id"],
            "canvas",
            filepath.stem,
        ]
    )
    escaped_identifier = "/".join(
        [
            config("COMMON_PATH_PREFIX"),
            arrangement["collection_id"],
            archival_object["component_id"],
            filepath.stem,
        ]
    )
    service_id = "/".join(
        [config("ALCHEMIST_IIIF_ENDPOINT").rstrip("/"), escaped_identifier]
    )
    resource_id = service_id + "/full/max/0/default.jpg"
    if sequence_indicators.get(archival_object["component_id"]):
        canvas_label = filepath.stem.split("_")[-1].lstrip("0")
    else:
        canvas_label = filepath.stem
    canvas = {
        "@type": "sc:Canvas",
        "@id": canvas_id,
        "label": canvas_label,
        "width": dimensions[0],
        "height": dimensions[1],
        "images": [
            {
                "@type": "oa:Annotation",
                "motivation": "sc:painting",
                "on": canvas_id,
                "resource": {
                    "@type": "dctypes:Image",
                    "@id": resource_id,
                    "service": {
                        "@context": "http://iiif.io/api/image/2/context.json",
                        "@id": service_id,
                        "profile": "http://iiif.io/api/image/2/level2.json",
                    },  # optional?
                },
            }
        ],
    }
    return canvas


def get_thumbnail_url(
    filepaths: list[Path], archival_object: dict, arrangement: dict
) -> str:
    source_file = Path(sorted(filepaths)[0])
    if source_file.suffix == ".mp4":
        return "/".join(
            [
                config("ALCHEMIST_BASE_URL").rstrip("/"),
                config("COMMON_PATH_PREFIX"),
                arrangement["collection_id"],
                archival_object["component_id"],
                "thumbnail.webp",
            ]
        )
    thumbnail_id = "/".join(
        [
            config("COMMON_PATH_PREFIX"),
            arrangement["collection_id"],
            archival_object[
                "component_id"
            ],  # TODO component_id is redundant for single file archival objects
            source_file.stem,
        ]
    )
    return "/".join(
        [
            config("ALCHEMIST_IIIF_ENDPOINT").rstrip("/"),
            thumbnail_id,
            "full",
            "200,",
            "0",
            "default.webp",
        ]
    )


def create_digital_object_file_versions(
    build_directory: tempfile.TemporaryDirectory[str],
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
) -> None:
    logger.debug(f"🐞 ARCHIVAL_OBJECT: {archival_object['component_id']}")
    logger.debug(f"🐞 BUILD_DIRECTORY: {build_directory}")

    archival_object_directory = (
        Path(build_directory.name)
        .joinpath(
            config("COMMON_PATH_PREFIX"),
            arrangement["collection_id"],
            archival_object["component_id"],
        )
        .resolve(strict=True)
    )
    logger.debug(f"🐞 ARCHIVAL_OBJECT_DIRECTORY: {archival_object_directory}")

    archival_object_page_url = "/".join(
        [
            config("ALCHEMIST_BASE_URL").rstrip("/"),
            config("COMMON_PATH_PREFIX"),
            arrangement["collection_id"],
            archival_object["component_id"],
        ]
    )
    logger.debug(f"🐞 ARCHIVAL_OBJECT_PAGE_URL: {archival_object_page_url}")

    filepaths = [
        f.absolute()
        for f in archival_object_directory.iterdir()
        if f.is_file() and (f.name.endswith(".ptif") or f.name.endswith(".mp4"))
    ]
    logger.debug(f"🐞 FILEPATHS[0]: {sorted(filepaths)[0]}")

    if filepaths[0].name.endswith(".ptif"):
        digital_object_type = "still_image"
    elif filepaths[0].name.endswith(".mp4"):
        digital_object_type = "moving_image"
    elif filepaths[0].name.endswith(".mp3"):
        digital_object_type = "sound_recording"
    else:
        digital_object_type = ""

    file_versions = [
        {
            "file_uri": get_thumbnail_url(filepaths, archival_object, arrangement),
            "jsonmodel_type": "file_version",
            "is_representative": True,
            "caption": archival_object["title"],
            "publish": True,
            "use_statement": "image-thumbnail",
            "xlink_show_attribute": "embed",
        },
        {
            "file_uri": archival_object_page_url,
            "jsonmodel_type": "file_version",
            "caption": f"{archival_object['title']} {digital_object_type.replace('_', ' ')}",
            "publish": True,
            "use_statement": "Web-Access",
        },
    ]

    digital_object_count = len(
        [i for i in archival_object["instances"] if "digital_object" in i.keys()]
    )
    logger.debug(f"🐞 DIGITAL OBJECT COUNT: {digital_object_count}")
    if digital_object_count > 1:
        raise ValueError(
            f"❌ MULTIPLE DIGITAL OBJECTS FOUND: {archival_object['component_id']}"
        )
    elif digital_object_count == 1:
        cascflow.save_digital_object_file_versions(archival_object, file_versions)
    elif digital_object_count < 1:
        # returns new archival_object with digital_object instance included
        (
            digital_object_uri,
            archival_object,
        ) = cascflow.create_digital_object(
            archival_object, digital_object_type=digital_object_type
        )
        cascflow.save_digital_object_file_versions(archival_object, file_versions)


def publish_archival_object_access_files(
    build_directory: tempfile.TemporaryDirectory[str],
    archival_object: dict,
    arrangement: dict,
) -> None:
    archival_object_access_path = "/".join(
        [
            config("COMMON_PATH_PREFIX"),
            arrangement["collection_id"],
            archival_object["component_id"],
        ]
    )
    try:
        s5cmd_sync = subprocess.run(
            [
                config("S5CMD_CMD"),
                "sync",
                f"{build_directory.name}/{archival_object_access_path}/*",
                f"s3://{config('S3_BUCKET')}/{archival_object_access_path}/",
            ],
            env={
                "AWS_ACCESS_KEY_ID": config("AWS_ACCESS_KEY_ID"),
                "AWS_SECRET_ACCESS_KEY": config("AWS_SECRET_ACCESS_KEY"),
            },
            capture_output=True,
            check=True,
            text=True,
        )
        for line in s5cmd_sync.stdout.splitlines():
            logger.debug(f"🐞 S5CMD SYNC OUTPUT: {line}")
    except:
        logger.exception("‼️")
        raise


def format_archival_object_creators_display(archival_object):
    # TODO check for creators higher up in the hierarchy
    creators = {}
    for linked_agent in archival_object.get("linked_agents", []):
        resolved = linked_agent.get("_resolved", {})
        if resolved.get("publish") and linked_agent.get("role") == "creator":
            sort_name = resolved.get("display_name", {}).get("sort_name", "")
            relator = linked_agent.get("relator")
            if relator:
                relator_label = LINKED_AGENT_ARCHIVAL_RECORD_RELATORS.get(
                    relator, relator
                )
                sort_name += f" [{relator_label}]"
            creators[linked_agent.get("ref", "")] = sort_name
    return creators


def format_archival_object_dates_display(archival_object):
    # NOTE begin and end could be: YYYY, YYYY-MM, YYYY-MM-DD
    months = {
        "01": "January",
        "02": "February",
        "03": "March",
        "04": "April",
        "05": "May",
        "06": "June",
        "07": "July",
        "08": "August",
        "09": "September",
        "10": "October",
        "11": "November",
        "12": "December",
    }
    dates_display = []
    for date in archival_object.get("dates", []):
        if date.get("label") == "creation":
            begin = date.get("begin", "")
            end = date.get("end", "")
            expression = date.get("expression", "")
            if end:
                if begin[:4] == end[:4]:
                    dates_display.append(
                        "{} to {}".format(
                            " ".join(
                                filter(
                                    None,
                                    [
                                        begin[:4],
                                        months.get(begin[5:7], ""),
                                        begin[8:10].lstrip("0"),
                                    ],
                                )
                            ),
                            " ".join(
                                filter(
                                    None,
                                    [
                                        months.get(end[5:7], ""),
                                        end[8:10].lstrip("0"),
                                    ],
                                )
                            ),
                        )
                    )
                else:
                    dates_display.append(
                        "{} to {}".format(
                            " ".join(
                                filter(
                                    None,
                                    [
                                        begin[:4],
                                        months.get(begin[5:7], ""),
                                        begin[8:10].lstrip("0"),
                                    ],
                                )
                            ),
                            " ".join(
                                filter(
                                    None,
                                    [
                                        end[:4],
                                        months.get(end[5:7], ""),
                                        end[8:10].lstrip("0"),
                                    ],
                                )
                            ),
                        )
                    )
            elif begin:
                dates_display.append(
                    " ".join(
                        filter(
                            None,
                            [
                                begin[:4],
                                months.get(begin[5:7], ""),
                                begin[8:10].lstrip("0"),
                            ],
                        )
                    )
                )
            elif expression:
                dates_display.append(expression)
    return dates_display


def format_archival_object_extents_display(archival_object):
    extents_display = []
    for extent in archival_object.get("extents", []):
        number = str(extent.get("number", "")).strip()
        extent_type = extent.get("extent_type", "")
        extents_display.append(f"{number} {extent_type}".strip())
    return extents_display


def format_archival_object_subjects_display(archival_object):
    subjects = {}
    for subject in archival_object.get("subjects", []):
        resolved = subject.get("_resolved", {})
        if resolved.get("publish"):
            subjects[subject.get("ref", "")] = resolved.get("title", "")
    # TODO check for subjects higher up in the hierarchy
    for linked_agent in archival_object.get("linked_agents", []):
        resolved = linked_agent.get("_resolved", {})
        if resolved.get("publish") and linked_agent.get("role") == "subject":
            sort_name = resolved.get("display_name", {}).get("sort_name", "")
            relator = linked_agent.get("relator")
            if relator:
                relator_label = LINKED_AGENT_ARCHIVAL_RECORD_RELATORS.get(
                    relator, relator
                )
                sort_name += f" [{relator_label}]"
            subjects[linked_agent.get("ref", "")] = sort_name
    return subjects


def format_archival_object_notes_display(archival_object):
    singlepart_note_types = {
        "abstract": "Abstract",
        "materialspec": "Materials Specific Details",
        "physdesc": "Physical Description",
        "physfacet": "Physical Facet",
        "physloc": "Physical Location",
    }
    multipart_note_types = {
        "accessrestrict": "Conditions Governing Access",
        "accruals": "Accruals",
        "acqinfo": "Immediate Source of Acquisition",
        "altformavail": "Existence and Location of Copies",
        "appraisal": "Appraisal",
        "arrangement": "Arrangement",
        "bioghist": "Biographical / Historical",
        "custodhist": "Custodial History",
        "dimensions": "Dimensions",
        "fileplan": "File Plan",
        "legalstatus": "Legal Status",
        "odd": "General",
        "originalsloc": "Existence and Location of Originals",
        "otherfindaid": "Other Finding Aids",
        "phystech": "Physical Characteristics and Technical Requirements",
        "prefercite": "Preferred Citation",
        "processinfo": "Processing Information",
        "relatedmaterial": "Related Materials",
        "scopecontent": "Scope and Contents",
        "separatedmaterial": "Separated Materials",
        "userestrict": "Conditions Governing Use",
    }
    notes_display = {}
    for note in archival_object.get("notes", []):
        if note.get("publish"):
            note_type = note.get("jsonmodel_type", "")
            note_key = note.get("type", "")
            if note_type == "note_singlepart":
                if note_key in singlepart_note_types:
                    note_label = note.get("label") or singlepart_note_types[note_key]
                    if note_label not in notes_display:
                        notes_display[note_label] = []
                    for content in note.get("content", []):
                        notes_display[note_label].append(content)
            elif note_type == "note_multipart":
                if note_key in multipart_note_types:
                    note_label = note.get("label") or multipart_note_types[note_key]
                    if note_label not in notes_display:
                        notes_display[note_label] = []
                    for subnote in note.get("subnotes", []):
                        if (
                            subnote.get("publish")
                            and subnote.get("jsonmodel_type") == "note_text"
                        ):
                            notes_display[note_label].append(subnote.get("content", ""))
                        # TODO elif subnote["jsonmodel_type"] == "note_chronology":
                        # TODO elif subnote["jsonmodel_type"] == "note_definedlist":
                        # TODO elif subnote["jsonmodel_type"] == "note_orderedlist":
            # TODO elif note["jsonmodel_type"] == "note_bibliography":
            # TODO elif note["jsonmodel_type"] == "note_index":
    return notes_display


def generate_archival_object_page(
    build_directory: tempfile.TemporaryDirectory[str],
    archival_object: dict,
    arrangement: dict,
    mimetype: str,
) -> None:
    try:
        logger.debug(f"🐞 BUILD_DIRECTORY.NAME: {build_directory.name}")
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(Path(__file__).parent / "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        if mimetype and mimetype.startswith("video/"):
            # TODO use IIIF Presentation API 3.0; manifest.json files can supply video
            # NOTE template currently only handles mp4 files
            template = environment.get_template("video.tpl")
            iiif_manifest_url = (
                f"{archival_object['component_id']}.{mimetype.split('/')[-1]}"
            )
        else:
            template = environment.get_template("archival_object.tpl")
            iiif_manifest_url = "/".join(
                [
                    config("ALCHEMIST_BASE_URL").rstrip("/"),
                    config("COMMON_PATH_PREFIX"),
                    arrangement["collection_id"],
                    archival_object["component_id"],
                    "manifest.json",
                ]
            )
        if arrangement.get("series_title"):
            series_display_string = arrangement["series_title"]
        else:
            series_display_string = arrangement.get("series_display_string")
        if arrangement.get("subseries_title"):
            subseries_display_string = arrangement["subseries_title"]
        else:
            subseries_display_string = arrangement.get("subseries_display_string")
        if arrangement.get("file_title"):
            file_display_string = arrangement["file_title"]
        else:
            file_display_string = arrangement.get("file_display_string")
        identifier_display = archival_object.get("component_id", "")
        creators = format_archival_object_creators_display(archival_object)
        dates_display = format_archival_object_dates_display(archival_object)
        extents_display = format_archival_object_extents_display(archival_object)
        subjects = format_archival_object_subjects_display(archival_object)
        notes_display = format_archival_object_notes_display(archival_object)
        archival_object_page_key = (
            Path(config("COMMON_PATH_PREFIX"))
            .joinpath(
                arrangement["collection_id"],
                archival_object["component_id"],
                "index.html",
            )
            .as_posix()
        )
        archival_object_page_file = (
            Path(build_directory.name).joinpath(archival_object_page_key).as_posix()
        )
        Path(archival_object_page_file).parent.mkdir(parents=True, exist_ok=True)
        with open(archival_object_page_file, "w") as f:
            # supply data to template placeholders
            f.write(
                template.render(
                    title=archival_object["title"],
                    collection=arrangement.get("collection_title"),
                    collection_uri=arrangement["collection_uri"],
                    series=series_display_string,
                    series_uri=arrangement.get("series_uri"),
                    subseries=subseries_display_string,
                    subseries_uri=arrangement.get("subseries_uri"),
                    file=file_display_string,
                    file_uri=arrangement.get("file_uri"),
                    identifier=identifier_display,
                    dates=dates_display,
                    creators=creators,
                    extents=extents_display,
                    subjects=subjects,
                    notes=notes_display,
                    archivesspace_public_url=config("ARCHIVESSPACE_PUBLIC_URL"),
                    archival_object_uri=archival_object["uri"],
                    iiif_manifest_url=iiif_manifest_url,
                    iiif_manifest_json=json.dumps({"manifest": f"{iiif_manifest_url}"}),
                    rights=RIGHTS_NOTICE_HTML,
                )
            )
        logger.info(
            f"✨ ARCHIVAL OBJECT PAGE FILE GENERATED: {archival_object_page_file}"
        )
    except Exception as e:
        logger.exception(e)
        raise


def generate_iiif_manifest(
    build_directory: tempfile.TemporaryDirectory[str],
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
    mimetype: str,
) -> None:
    if mimetype == "video/mp4":
        # TODO use IIIF Presentation API 3.0; manifest.json files can supply video
        return
    metadata = []
    if arrangement.get("collection_title"):
        metadata.append(
            {
                "label": "Collection",
                "value": arrangement["collection_title"],
            }
        )
    if arrangement.get("series_title"):
        metadata.append({"label": "Series", "value": arrangement["series_title"]})
    elif arrangement.get("series_display_string"):
        metadata.append(
            {
                "label": "Series",
                "value": arrangement["series_display_string"],
            }
        )
    if arrangement.get("subseries_title"):
        metadata.append(
            {
                "label": "Sub-Series",
                "value": arrangement["subseries_title"],
            }
        )
    elif arrangement.get("subseries_display_string"):
        metadata.append(
            {
                "label": "Sub-Series",
                "value": arrangement["subseries_display_string"],
            }
        )
    if arrangement.get("file_title"):
        metadata.append(
            {
                "label": "File",
                "value": arrangement["file_title"],
            }
        )
    elif arrangement.get("file_display_string"):
        metadata.append(
            {
                "label": "File",
                "value": arrangement["file_display_string"],
            }
        )
    if archival_object["component_id"]:
        metadata.append(
            {
                "label": "Identifier",
                "value": archival_object["component_id"],
            }
        )
    dates = format_archival_object_dates_display(archival_object)
    if dates:
        metadata.append({"label": "Dates", "value": dates})
    creators = format_archival_object_creators_display(archival_object)
    if creators:
        metadata.append({"label": "Creators", "value": list(creators.values())})
    extents = format_archival_object_extents_display(archival_object)
    if extents:
        metadata.append({"label": "Extents", "value": extents})
    subjects = format_archival_object_subjects_display(archival_object)
    if subjects:
        metadata.append({"label": "Subjects", "value": list(subjects.values())})
    notes = format_archival_object_notes_display(archival_object)
    description = ""
    attribution = RIGHTS_NOTICE_HTML
    if notes:
        for note_label, note_contents in notes.items():
            if note_contents:
                metadata.append({"label": note_label, "value": note_contents})
            if note_label == "Scope and Contents":
                description = note_contents
            if note_label == "Conditions Governing Use":
                # TODO check for note upwards in the hierarchy
                # TODO validate against Restriction End date
                attribution = note_contents
    # Use an existing manifiest file if we are only updating metadata and have no filepaths.
    if not filepaths:
        manifest_key = (
            Path(config("COMMON_PATH_PREFIX"))
            .joinpath(
                arrangement["collection_id"],
                archival_object["component_id"],
                "manifest.json",
            )
            .as_posix()
        )
        response = cascflow.s3_get_object(config("S3_BUCKET"), manifest_key)
        if response is None:
            raise FileNotFoundError(f"❌ MANIFEST NOT FOUND IN S3: {manifest_key}")
        manifest = json.loads(response["Body"].read())
    else:
        manifest: dict[str, Any] = {
            "@context": "http://iiif.io/api/presentation/2/context.json",
            "@type": "sc:Manifest",
            "@id": "/".join(
                [
                    config("ALCHEMIST_BASE_URL").rstrip("/"),
                    config("COMMON_PATH_PREFIX"),
                    arrangement["collection_id"],
                    archival_object["component_id"],
                    "manifest.json",
                ]
            ),
        }
    # maintain order of keys
    manifest["label"] = archival_object["title"]
    if description:
        manifest["description"] = description
    # Update thumbnail if we have filepaths.
    if filepaths:
        manifest.update(
            {
                "thumbnail": {
                    "@id": get_thumbnail_url(filepaths, archival_object, arrangement),
                    "service": {
                        "@context": "http://iiif.io/api/image/2/context.json",
                        "@id": get_thumbnail_url(
                            filepaths, archival_object, arrangement
                        ).rsplit("/", maxsplit=4)[0],
                        "profile": "http://iiif.io/api/image/2/level1.json",
                    },
                }
            }
        )
    manifest["metadata"] = metadata
    if attribution:
        manifest["attribution"] = attribution
    # Update sequence indicators and canvas metadata if we have filepaths.
    if filepaths:
        manifest.update({"sequences": [{"@type": "sc:Sequence", "canvases": []}]})
        # Check all filepaths for valid sequence indicators.
        sequence_indicators = {
            archival_object["component_id"]: has_valid_sequence_indicators(filepaths)
        }
        with ProcessPoolExecutor() as executor:
            futures = [
                executor.submit(
                    create_canvas_metadata,
                    filepath,
                    archival_object,
                    arrangement,
                    sequence_indicators,
                )
                for filepath in sorted(filepaths)
            ]
            # maintain the order of the filepaths
            for future in futures:
                logger.debug(f"🐞 CANVAS: {future.result()}")
                # add canvas to sequences
                manifest["sequences"][0]["canvases"].append(future.result())
    # save manifest file
    manifest_file = Path(build_directory.name).joinpath(
        config("COMMON_PATH_PREFIX"),
        arrangement["collection_id"],
        archival_object["component_id"],
        "manifest.json",
    )
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_file, "w") as f:
        f.write(json.dumps(manifest, indent=4))
    logger.info(f"✨ MANIFEST FILE GENERATED: {manifest_file}")


def create_pyramid_tiff(
    build_directory: tempfile.TemporaryDirectory[str],
    filepath: Path,
    archival_object: dict,
    arrangement: dict,
) -> None:
    try:
        # NOTE vips has problems with JP2 source images
        magick_identify = subprocess.run(
            [
                config("MAGICK_CMD"),
                "identify",
                "-format",
                "%m",
                filepath.as_posix(),
            ],
            capture_output=True,
            check=True,
            text=True,
        )

        if magick_identify.stdout.strip() == "JP2":
            vips_source_image = (
                Path(build_directory.name)
                .joinpath(f"{filepath.stem}.tmp.tiff")
                .as_posix()
            )
            subprocess.run(
                [
                    config("MAGICK_CMD"),
                    "convert",
                    "-quiet",
                    filepath.as_posix(),
                    "-compress",
                    "None",
                    vips_source_image,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            vips_source_image = filepath.as_posix()
        pyramid_tiff_key = "/".join(
            [
                config("COMMON_PATH_PREFIX"),
                arrangement["collection_id"],
                archival_object["component_id"],
                f"{filepath.stem}.ptif",
            ]
        )
        pyramid_tiff_file = (
            Path(build_directory.name).joinpath(pyramid_tiff_key).as_posix()
        )
        subprocess.run(
            [
                config("VIPS_CMD"),
                "tiffsave",
                vips_source_image,
                pyramid_tiff_file,
                "--tile",
                "--pyramid",
                "--compression",
                "jpeg",
                "--tile-width",
                "256",
                "--tile-height",
                "256",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.debug(f"🐞 PYRAMID TIFF CREATED: {pyramid_tiff_file}")
        if vips_source_image.endswith(".tmp.tiff"):
            Path(vips_source_image).unlink()
    except Exception as e:
        logger.exception(e)
        raise


def conditional_derivative_file_processing(
    build_directory: tempfile.TemporaryDirectory[str],
    filepath: Path,
    archival_object: dict,
    arrangement: dict,
) -> None:
    type, encoding = mimetypes.guess_type(filepath.as_posix())

    if not type:
        logger.error("❌ UNKNOWN MIME TYPE: %s", filepath.name)
        return

    if type.startswith("image/"):
        create_pyramid_tiff(build_directory, filepath, archival_object, arrangement)
    elif type.startswith("video/"):
        video_key = "/".join(
            [
                config("COMMON_PATH_PREFIX"),
                arrangement["collection_id"],
                archival_object["component_id"],
                filepath.name,
            ]
        )
        video_file_path = Path(build_directory.name).joinpath(video_key)
        try:
            video_file_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, video_file_path)
            # create a thumbnail from the midpoint of the video
            duration = subprocess.run(
                [
                    config("FFPROBE_CMD"),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_file_path.as_posix(),
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            midpoint = str(float(duration) / 2)
            subprocess.run(
                [
                    config("FFMPEG_CMD"),
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    midpoint,
                    "-i",
                    video_file_path.as_posix(),
                    "-vframes",
                    "1",
                    "-vf",
                    "scale=200:-1",
                    video_file_path.parent.joinpath("thumbnail.webp").as_posix(),
                ],
                check=True,
            )
        except Exception:
            logger.exception(f"❌ VIDEO FILE COPY FAILED: {filepath}")
        else:
            logger.info(f"☑️ VIDEO FILE COPIED: {video_key}")
    else:
        logger.error(
            "❌ {} FILES ARE NOT SUPPORTED AT THIS TIME: {}".format(type, filepath.name)
        )


def loop_over_archival_object_files(
    build_directory: tempfile.TemporaryDirectory[str],
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
) -> None:
    """Concurrently process files in the filepaths list."""
    with ProcessPoolExecutor() as executor:
        [
            executor.submit(
                conditional_derivative_file_processing,
                build_directory,
                filepath,
                archival_object,
                arrangement,
            )
            for filepath in filepaths
        ]


def archival_object_level_processing(
    build_directory: tempfile.TemporaryDirectory[str],
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
) -> None:
    logger.info(f"ℹ️  {archival_object['component_id']}")
    # TODO consider conditions for identifiying non-image file types
    mimetype = ""
    if filepaths and len(filepaths) == 1:
        type, encoding = mimetypes.guess_type(filepaths[0].as_posix())
        if type == "video/mp4":
            mimetype = type
    generate_archival_object_page(
        build_directory, archival_object, arrangement, mimetype
    )
    # `filepaths`` is set to [] if we are only updating metadata.
    generate_iiif_manifest(
        build_directory, filepaths, archival_object, arrangement, mimetype
    )
    if filepaths:
        loop_over_archival_object_files(
            build_directory, filepaths, archival_object, arrangement
        )
        logger.info(
            f"☑️  DERIVATIVE FILE PROCESSING COMPLETE: {archival_object['component_id']}"
        )


def _parse_indicator(stem: str) -> tuple[int, str | None] | None:
    """
    Parses the sequence indicator from a filename stem.
    Returns (numeric_part, suffix) where suffix is 'r', 'v', or None,
    or returns None if the stem is invalid.
    """
    components = stem.split("_")
    if len(components) < 2:
        return None
    last = components[-1]
    # Use tuple form of endswith to check for either suffix in one call
    if last.endswith(("r", "v")):
        digits, rv = last[:-1], last[-1]
    else:
        digits, rv = last, None
    if not (digits.isdigit() and len(digits) >= 2):
        return None
    return (int(digits), rv)


def has_valid_sequence_indicators(filepaths) -> bool:
    """
    Returns True if all filepaths have a valid sequence indicator (digits,
    optionally followed by 'r' or 'v'), and the numeric part forms a
    contiguous sequence. Recto/verso logic: if 'r' or 'v' exists for a
    number, both must exist and no bare number may exist for that position.
    Accepts a list of Path objects or strings.
    """
    # This function should only be called with a non-empty list; raise
    # explicitly rather than letting sorted() or indexing fail silently later
    if not filepaths:
        raise ValueError("filepaths must not be empty")

    # Parse and validate each stem
    indicators = []
    for fp in filepaths:
        indicator = _parse_indicator(Path(fp).stem)
        if indicator is None:
            return False  # Invalid indicator found, return early
        indicators.append(indicator)

    # Group suffixes ('r', 'v', or None) by their numeric part,
    # e.g. [('2', 'r'), ('2', 'v'), ('3', None)] -> {2: {'r', 'v'}, 3: {None}}
    seq_map: defaultdict[int, set] = defaultdict(set)
    for num, rv in indicators:
        seq_map[num].add(rv)

    # Check for a contiguous sequence: numbers must form an unbroken range,
    # e.g. [1, 2, 3] is valid but [1, 3] is not
    nums = sorted(seq_map)
    if nums != list(range(nums[0], nums[-1] + 1)):
        return False

    # Each number must be in exactly one of two valid states:
    # - {'r', 'v'}: both recto and verso present, no bare number
    # - {None}:     bare number only, no recto/verso suffixes
    return all(rv_set == {"r", "v"} or rv_set == {None} for rv_set in seq_map.values())


def is_archival_object_eligible_for_publication(
    archival_object: dict, pipeline: str
) -> bool:
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
        digital_object_instances = [
            instance
            for instance in archival_object["instances"]
            if "digital_object" in instance.keys()
        ]
        digital_object_count = len(digital_object_instances)
        if digital_object_count > 1:
            message = "‼️ MULTIPLE DIGITAL OBJECTS FOUND: [**{}**]({}/resolve/readonly?uri={})".format(
                archival_object["title"],
                config("ARCHIVESSPACE_STAFF_URL"),
                archival_object["uri"],
            )
            logger.error(message)
            return False
        elif digital_object_count == 1:
            instance = digital_object_instances[0]
            if (
                instance["digital_object"]["_resolved"].get("file_versions")
                and pipeline == "publication"
            ):
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
    type, encoding = mimetypes.guess_type(entry.as_posix())
    ## TODO set supported types in configuration
    if type and (type.startswith("image/") or type.endswith("/mp4")):
        return True
    else:
        return False


def validate_digital_files_for_publication(
    validation_results: dict, pipeline: str
) -> None:
    source_path = validation_results.get("source_path")
    if not source_path:
        logger.error("❌ SOURCE PATH NOT FOUND IN VALIDATION RESULTS")
        return
    source_path = Path(source_path)
    eligible_archival_objects = []
    ineligible_archival_objects = []
    nested_directories = validation_results.get("nested_directories", [])
    empty_directories = validation_results.get("empty_directories", [])
    file_count = validation_results.get("file_count", 0)
    unsupported_files = []
    sequence_indicators = {}
    # get the cached archival object data from validation_results
    cached_archival_objects = validation_results.get("eligible_archival_objects", {})
    logger.info(
        f"{next(iter(cached_archival_objects))}{', …' if len(cached_archival_objects) > 1 else ''}"
    )
    ## iterate over the first level of entries in the source directory
    for entry in source_path.iterdir():
        ## validate the entry (file or directory) using cached data
        if entry.stem in cached_archival_objects:
            archival_object = cached_archival_objects[entry.stem]
            if is_archival_object_eligible_for_publication(archival_object, pipeline):
                eligible_archival_objects.append(entry.stem)
            else:
                ineligible_archival_objects.append(entry.stem)
        if entry.is_file():
            ## check for file types that are unsupported in publication
            if not is_publication_file_supported(entry):
                unsupported_files.append(entry)
        if entry.is_dir():
            # Check all files in the directory for valid sequence indicators.
            children = [child for child in entry.iterdir() if child.is_file()]
            sequence_indicators[entry.stem] = has_valid_sequence_indicators(children)
            for child in children:
                if not is_publication_file_supported(child):
                    unsupported_files.append(child)
    ## messaging
    if eligible_archival_objects:
        for eligible_archival_object in eligible_archival_objects:
            logger.info(f"🉑 {eligible_archival_object}")
            if sequence_indicators.get(eligible_archival_object):
                logger.info("🔢 THUMBNAILS WILL BE LABELED WITH SEQUENTIAL INDICATORS")
            else:
                logger.info("🔠 THUMBNAILS WILL BE LABELED WITH FULL FILENAMES")
        logger.info(f"🗂 ARCHIVAL OBJECT COUNT: {len(eligible_archival_objects)}")
        logger.info(f"📄 FILE COUNT: {file_count}")
    ## validation and messaging
    if file_count == 0:
        message = "❌ NO FILES FOUND"
        logger.error(message)
        raise FileNotFoundError(message)
    if ineligible_archival_objects:
        message = "❌ INELIGIBLE ARCHIVAL OBJECTS FOUND"
        logger.error(message)
        for ineligible_archival_object in ineligible_archival_objects:
            logger.error(f"❌ {ineligible_archival_object}")
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
    global args, config, logger
    args = parser.parse_args()

    # set up settings path and logging
    if args.settings is not None:
        settings_path = Path(args.settings).expanduser().resolve()
    else:
        settings_path = Path(__file__).parent.joinpath("settings.ini").resolve()
    if not settings_path.exists():
        raise FileNotFoundError(f"Settings file not found: {settings_path}")
    # configure cascflow to use our settings.ini file
    config_instance = Config(RepositoryIni(settings_path.as_posix()))
    cascflow.set_config(config_instance)
    # reassign module-level config to use the cascflow config instance with our settings
    config = cascflow.config  # Use cascflow.config everywhere as config()

    cascflow.setup_logging(str(settings_path))
    logger = logging.getLogger("alchemist")

    # handle the commands
    logger.debug(f"🐞 TARGET: {getattr(args, 'target', None)}")
    if args.command == "validate":
        if args.target == "metadata":
            logger.info(args.context)
            cascflow.validate_metadata_identifier(args.context)
        else:
            validation_results = cascflow.validate_digital_files(args.context)
            validate_digital_files_for_publication(validation_results, args.target)
    elif args.command == "execute":
        build_directory = tempfile.TemporaryDirectory()
        if args.target == "metadata":
            # The context is an identifier string.
            validation_results = cascflow.validate_metadata_identifier(args.context)
            arrangement = None
            for component_id, archival_object in validation_results.get(
                "eligible_archival_objects", {}
            ).items():
                arrangement = cascflow.get_arrangement(archival_object)
                filepaths = []
                archival_object_level_processing(
                    build_directory, filepaths, archival_object, arrangement
                )
                publish_archival_object_access_files(
                    build_directory, archival_object, arrangement
                )
            if validation_results.get("identifier_level") == "resource":
                if config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID", default=False):
                    # Invalidate everything under the resource path component.
                    invalidate_cloudfront_paths(
                        paths=[f"/{config('COMMON_PATH_PREFIX')}/{args.context}/*"]
                    )
            else:
                if config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID", default=False):
                    # We should only have a single archival object.
                    if arrangement is not None:
                        invalidate_cloudfront_paths(
                            paths=[
                                f"/{config('COMMON_PATH_PREFIX')}/{arrangement['collection_id']}/{args.context}/*"
                            ]
                        )
        else:
            # Our target is either "publication" or "files". The context is the volume name.
            batch_set_id = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
            cloudfront_invalidation_batch = []
            for (
                batch_directory,
                stage_2_path_obj,
                filepaths,
                archival_object,
                arrangement,
            ) in cascflow.execute(args.context, batch_set_id, args.target):
                # process each result as it is yielded
                archival_object_level_processing(
                    build_directory, filepaths, archival_object, arrangement
                )
                publish_archival_object_access_files(
                    build_directory, archival_object, arrangement
                )
                create_digital_object_file_versions(
                    build_directory, filepaths, archival_object, arrangement
                )
                cascflow.move_to_stage_3(stage_2_path_obj, batch_directory)
                if args.target == "files":
                    # Invalidate the paths for the updated files.
                    cloudfront_invalidation_batch.append(
                        "/".join(
                            [
                                "",  ## start with a leading slash
                                config("COMMON_PATH_PREFIX"),
                                arrangement["collection_id"],
                                archival_object["component_id"],
                                "*",  ## end with a wildcard
                            ]
                        )
                    )
            if args.target == "files" and cloudfront_invalidation_batch:
                invalidate_cloudfront_paths(paths=cloudfront_invalidation_batch)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
