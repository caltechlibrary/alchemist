# file: alchemist.py
# RENDER AND PUBLISH ACCESS PAGES AND ASSETS

import argparse
import datetime
import json
import logging
import math
import mimetypes
import shutil
import subprocess
import tempfile
import time

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import boto3  # pypi: boto3
import jinja2  # pypi: Jinja2

from botocore.config import Config as BotoClientConfig  # pypi: boto3
from decouple import Config, RepositoryIni  # pypi: python-decouple

import arkminter
import cascflow

# tile size (in pixels) used for both generating pyramid TIFFs (vips) and
# calculating the resulting pyramid level ("pages") count for serverless-iiif
PYRAMID_TILE_SIZE = 256

# worker threads for attaching x-amz-meta- headers to pyramid TIFFs already
# in S3; these are network-bound metadata-only copies, not data transfer
PYRAMID_TIFF_METADATA_MAX_WORKERS = 20

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
settings_path = None
config = cascflow.config
logger = logging.getLogger("alchemist")

ALCHEMIST_SETTINGS_SPEC = [
    {"key": "AWS_ACCESS_KEY_ID", "kind": "string"},
    {"key": "AWS_SECRET_ACCESS_KEY", "kind": "string"},
    {"key": "ALCHEMIST_BUCKET", "kind": "string"},
    {"key": "ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID", "kind": "string", "required": False},
    {"key": "IIIF_CLOUDFRONT_DISTRIBUTION_ID", "kind": "string", "required": False},
    {"key": "ALCHEMIST_BASE_URL", "kind": "url"},
    {"key": "ALCHEMIST_IIIF_ENDPOINT", "kind": "url"},
    {"key": "ARCHIVESSPACE_PUBLIC_URL", "kind": "url"},
    {"key": "ARCHIVESSPACE_STAFF_URL", "kind": "url"},
    {"key": "ARCHIVESSPACE_API_URL", "kind": "url"},
    {"key": "ARCHIVESSPACE_USERNAME", "kind": "string"},
    {"key": "ARCHIVESSPACE_PASSWORD", "kind": "string"},
    {"key": "ARCHIVESSPACE_REPOSITORY_ID", "kind": "int", "required": False},
    {"key": "OUR_NMA", "kind": "url"},
    {"key": "OUR_NAAN", "kind": "string"},
    {"key": "OUR_SHOULDER", "kind": "string", "required": False},
    {"key": "RESOLVER_BUCKET", "kind": "string"},
    {"key": "MAGICK_CMD", "kind": "executable"},
    {"key": "VIPS_CMD", "kind": "executable"},
    {"key": "FFPROBE_CMD", "kind": "executable"},
    {"key": "FFMPEG_CMD", "kind": "executable"},
    {"key": "S5CMD_CMD", "kind": "executable"},
    {"key": "ABSOLUTE_MOUNT_PARENT", "kind": "directory"},
    {"key": "RELATIVE_SOURCE_DIRECTORY", "kind": "string"},
    {"key": "RELATIVE_BATCH_DIRECTORY", "kind": "string"},
    {"key": "FILES_TO_REMOVE", "kind": "csv", "required": False},
]


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


def _worker_init(sp: str) -> None:
    """Initialize worker process config from a settings.ini path (sp)."""
    cascflow.set_config(Config(RepositoryIni(sp)))


def invalidate_cloudfront_paths(distribution=None, paths=None, caller_reference=None):
    if distribution is None:
        distribution = config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID")
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
        DistributionId=distribution,
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
        DistributionId=distribution,
        Id=response["Invalidation"]["Id"],
    )
    logger.debug("🐞 CLOUDFRONT INVALIDATION COMPLETE")


def create_canvas_metadata(
    filepath: Path, archival_object: dict, sequence_indicator: str
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
            # TODO handle potential ARK Qualifier upstream
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[1],
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[2],
            "canvas",
            sequence_indicator,
        ]
    )
    escaped_identifier = "/".join(
        [
            # TODO handle potential ARK Qualifier upstream
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[1],
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[2],
            sequence_indicator,
        ]
    )
    service_id = "/".join(
        [config("ALCHEMIST_IIIF_ENDPOINT").rstrip("/"), escaped_identifier]
    )
    resource_id = service_id + "/full/max/0/default.jpg"
    canvas = {
        "@type": "sc:Canvas",
        "@id": canvas_id,
        "label": sequence_indicator,
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
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
    sequenced_filepaths: dict[str, Path],
) -> str:
    if next(iter(sequenced_filepaths.values())).suffix == ".mp4":
        return "/".join(
            [
                config("ALCHEMIST_BASE_URL").rstrip("/"),
                # TODO handle potential ARK Qualifier upstream
                archival_object["external_ark_url"]
                .split(config("OUR_NMA"))[-1]
                .split("/")[1],
                archival_object["external_ark_url"]
                .split(config("OUR_NMA"))[-1]
                .split("/")[2],
                "thumbnail.webp",
            ]
        )
    thumbnail_id = "/".join(
        [
            # TODO handle potential ARK Qualifier upstream
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[1],
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[2],
            next(iter(sequenced_filepaths.keys())),
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
    sequenced_filepaths: dict[str, Path],
) -> None:
    logger.debug(f"🐞 ARCHIVAL_OBJECT: {archival_object['component_id']}")
    logger.debug(f"🐞 BUILD_DIRECTORY: {build_directory}")

    archival_object_directory = (
        Path(build_directory.name)
        .joinpath(
            arrangement["collection_id"],
            archival_object["component_id"],
        )
        .resolve(strict=True)
    )
    logger.debug(f"🐞 ARCHIVAL_OBJECT_DIRECTORY: {archival_object_directory}")

    archival_object_page_url = "/".join(
        [
            config("ALCHEMIST_BASE_URL").rstrip("/"),
            # TODO handle potential ARK Qualifier upstream
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[1],
            archival_object["external_ark_url"]
            .split(config("OUR_NMA"))[-1]
            .split("/")[2],
        ]
    )
    logger.info(f"✨ ARCHIVAL OBJECT PAGE URL: {archival_object_page_url}")

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
        # NOTE thumbnail must come first so that it gets linked to the other published file version
        # > When a Digital Object or Digital Object Component record contains
        # > multiple published File Versions, the order of the File Versions
        # > affects the linking functionality of the representative image in
        # > the public user interface.
        # https://archivesspace.atlassian.net/wiki/x/CYCKy#%E2%80%9CMake-Representative%E2%80%9D-and-Digital-Object-Record-display-on-the-Public-User-Interface
        {
            "file_uri": get_thumbnail_url(
                filepaths, archival_object, arrangement, sequenced_filepaths
            ),
            "jsonmodel_type": "file_version",
            "is_representative": True,
            # NOTE caption appears as the thumbnail caption on the Digital Object record in the Public UI
            # without the caption the thumbnail appears captionless on the Digital Object record in the Public UI
            "caption": archival_object["title"],
            "publish": True,
            "use_statement": "image-thumbnail",
            "xlink_show_attribute": "embed",
            # NOTE setting file_format_name to jpeg causes the thumbnail to appear in the Staff UI
            # https://archivesspace.atlassian.net/wiki/x/CYCKy#Digital-Object-display-in-the-Staff-User-Interface
            "file_format_name": "jpeg",
        },
        {
            "file_uri": archival_object["external_ark_url"],
            "jsonmodel_type": "file_version",
            # NOTE caption appears as the Additional File Versions link text on the Digital Object record in the Public UI;
            # without the caption the Additional File Versions link text is the use_statement value
            "caption": archival_object["title"],
            "publish": True,
            "use_statement": "Persistent-URL",
        },
        {
            "file_uri": archival_object_page_url,
            "jsonmodel_type": "file_version",
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


def update_digital_object_metadata(archival_object: dict) -> None:
    """Sync an existing Digital Object's title and File Version captions
    with the current Archival Object title.

    Used by the metadata-only pipeline, where no derivative files are
    rebuilt so create_digital_object_file_versions() cannot run. Human
    archivists do not edit Digital Object records directly, so Alchemist
    must propagate title changes made on the Archival Object itself.
    """
    digital_object_instances = [
        instance
        for instance in archival_object["instances"]
        if "digital_object" in instance.keys()
    ]
    digital_object_count = len(digital_object_instances)
    if digital_object_count > 1:
        raise ValueError(
            f"❌ MULTIPLE DIGITAL OBJECTS FOUND: {archival_object['component_id']}"
        )
    elif digital_object_count == 1:
        digital_object = digital_object_instances[0]["digital_object"]["_resolved"]
        file_versions = digital_object.get("file_versions")
        if not file_versions:
            # nothing published yet for this archival_object's digital_object
            return
        for file_version in file_versions:
            # NOTE these are the only two captions derived from archival_object["title"];
            # see create_digital_object_file_versions()
            if file_version.get("use_statement") in (
                "image-thumbnail",
                "Persistent-URL",
            ):
                file_version["caption"] = archival_object["title"]
        digital_object["title"] = archival_object["title"]
        digital_object["file_versions"] = file_versions
        cascflow.update_digital_object(digital_object["uri"], digital_object)
        logger.info(
            f"✨ DIGITAL OBJECT TITLE AND FILE VERSION CAPTIONS UPDATED: {archival_object['component_id']}"
        )


def publish_archival_object_access_files(
    build_directory: tempfile.TemporaryDirectory[str],
    archival_object: dict,
    arrangement: dict,
) -> None:
    archival_object_access_path = "/".join(
        [
            arrangement["collection_id"],
            archival_object["component_id"],
        ]
    )
    # TODO handle potential ARK Qualifier upstream
    our_ark = f"{archival_object['external_ark_url'].split(config('OUR_NMA'))[-1].split('/')[1]}/{archival_object['external_ark_url'].split(config('OUR_NMA'))[-1].split('/')[2]}"
    try:
        s5cmd_sync = subprocess.run(
            [
                config("S5CMD_CMD"),
                "sync",
                "--exclude",
                "*.metadata.json",
                f"{build_directory.name}/{archival_object_access_path}/*",
                f"s3://{config('ALCHEMIST_BUCKET')}/{our_ark}/",
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
    except subprocess.CalledProcessError as e:
        logger.exception("‼️")
        logger.debug("🐞 S5CMD STDOUT:", e.stdout)
        logger.debug("🐞 S5CMD STDERR:", e.stderr)
        raise
    # pyramid TIFFs carry a `.metadata.json` sidecar (written by
    # create_pyramid_tiff()) with width/height/pages, so serverless-iiif can
    # read them back as x-amz-meta- headers instead of recalculating them on
    # every image request. `s5cmd sync --metadata` only accepts one uniform
    # value for the whole batch, so metadata is attached per-file here via a
    # same-key S3 copy (no bulk transfer involved, so plain boto3 rather
    # than s5cmd, which is used above for its parallel bulk-transfer speed).
    # These are network-bound, not CPU-bound, so a thread pool (rather than
    # the ProcessPoolExecutor used elsewhere in this file) is dispatched to
    # overlap the request latency across many files at once; the client's
    # connection pool is sized to match so threads aren't left waiting on it.
    bucket = config("ALCHEMIST_BUCKET")
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=config("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=config("AWS_SECRET_ACCESS_KEY"),
        config=BotoClientConfig(max_pool_connections=PYRAMID_TIFF_METADATA_MAX_WORKERS),
    )
    metadata_files = list(
        Path(build_directory.name, archival_object_access_path).glob(
            "*.ptif.metadata.json"
        )
    )
    with ThreadPoolExecutor(max_workers=PYRAMID_TIFF_METADATA_MAX_WORKERS) as executor:
        list(
            executor.map(
                lambda metadata_file: _update_pyramid_tiff_metadata(
                    s3_client, bucket, our_ark, metadata_file
                ),
                metadata_files,
            )
        )


def _update_pyramid_tiff_metadata(
    s3_client, bucket: str, our_ark: str, metadata_file: Path
) -> None:
    with open(metadata_file) as f:
        metadata = json.load(f)
    key = f"{our_ark}/{metadata_file.name.removesuffix('.metadata.json')}"
    # MetadataDirective="REPLACE" resets ContentType (and any other system
    # metadata not explicitly repeated) to a service default rather than
    # preserving it -- pyramid TIFFs should always be image/tiff rather than
    # s5cmd's generic application/octet-stream fallback for the .ptif extension.
    s3_client.copy_object(
        Bucket=bucket,
        Key=key,
        CopySource={"Bucket": bucket, "Key": key},
        Metadata={name: str(value) for name, value in metadata.items()},
        MetadataDirective="REPLACE",
        ContentType="image/tiff",
    )
    logger.debug(f"🐞 S3 METADATA UPDATED: {key} {metadata}")


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
            # TODO Q: should this be a resolver link instead of a direct link to the manifest file?
            # Leaning towards resolver link, but we must ensure Suffix Passthrough on the resolver,
            # and that our external_ark_url does not have a Qualifier.
            iiif_manifest_url = "/".join(
                [
                    config("ALCHEMIST_BASE_URL").rstrip("/"),
                    # TODO handle potential ARK Qualifier upstream
                    archival_object["external_ark_url"]
                    .split(config("OUR_NMA"))[-1]
                    .split("/")[1],
                    archival_object["external_ark_url"]
                    .split(config("OUR_NMA"))[-1]
                    .split("/")[2],
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
        archival_object_page_key = "/".join(
            [
                arrangement["collection_id"],
                archival_object["component_id"],
                "index.html",
            ]
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
                    iiif_manifest_json=json.dumps({"manifest": iiif_manifest_url}),
                    rights=RIGHTS_NOTICE_HTML,
                )
            )
        logger.debug(
            f"🐞 ARCHIVAL OBJECT PAGE FILE GENERATED: {archival_object_page_file}"
        )
    except Exception as e:
        logger.exception(e)
        raise


def get_sequence_indicator(filepath):
    seq = filepath.stem.split("_")[-1] if "_" in filepath.stem else filepath.stem
    num = seq.rstrip("rv")
    suffix = seq[len(num) :]
    padded = num.zfill(4)
    return f"{padded}{suffix}".lower()


def generate_iiif_manifest(
    build_directory: tempfile.TemporaryDirectory[str],
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
    mimetype: str,
    sequenced_filepaths: dict[str, Path],
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
    if not sequenced_filepaths:
        manifest_key = "/".join(
            [
                # TODO handle potential ARK Qualifier upstream
                archival_object["external_ark_url"]
                .split(config("OUR_NMA"))[-1]
                .split("/")[1],
                archival_object["external_ark_url"]
                .split(config("OUR_NMA"))[-1]
                .split("/")[2],
                "manifest.json",
            ]
        )
        response = cascflow.s3_get_object(config("ALCHEMIST_BUCKET"), manifest_key)
        if response is None:
            raise FileNotFoundError(f"❌ MANIFEST NOT FOUND IN S3: {manifest_key}")
        manifest = json.loads(response["Body"].read())
    else:
        # TODO manifest @id should be the resolver link, not a direct link to
        # the manifest file; ensure Suffix Passthrough on resolver and that our
        # external_ark_url does not have a Qualifier
        manifest: dict[str, Any] = {
            "@context": "http://iiif.io/api/presentation/2/context.json",
            "@type": "sc:Manifest",
            "@id": "/".join(
                [
                    config("ALCHEMIST_BASE_URL").rstrip("/"),
                    # TODO handle potential ARK Qualifier upstream
                    archival_object["external_ark_url"]
                    .split(config("OUR_NMA"))[-1]
                    .split("/")[1],
                    archival_object["external_ark_url"]
                    .split(config("OUR_NMA"))[-1]
                    .split("/")[2],
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
                    "@id": get_thumbnail_url(
                        filepaths, archival_object, arrangement, sequenced_filepaths
                    ),
                    "service": {
                        "@context": "http://iiif.io/api/image/2/context.json",
                        "@id": get_thumbnail_url(
                            filepaths, archival_object, arrangement, sequenced_filepaths
                        ).rsplit("/", maxsplit=4)[0],
                        "profile": "http://iiif.io/api/image/2/level1.json",
                    },
                }
            }
        )
    manifest["metadata"] = metadata
    if attribution:
        manifest["attribution"] = attribution
    # Update sequence indicators and canvas metadata if we have sequenced_filepaths.
    if sequenced_filepaths:
        manifest.update({"sequences": [{"@type": "sc:Sequence", "canvases": []}]})
        with ProcessPoolExecutor(
            initializer=_worker_init, initargs=(str(settings_path),)
        ) as executor:
            futures = [
                executor.submit(
                    create_canvas_metadata,
                    filepath,
                    archival_object,
                    sequence_indicator,
                )
                for sequence_indicator, filepath in sequenced_filepaths.items()
            ]
            # maintain the order of the filepaths (now sorted by sequence)
            for future in futures:
                logger.debug(f"🐞 CANVAS: {future.result()}")
                # add canvas to sequences
                manifest["sequences"][0]["canvases"].append(future.result())
    # save manifest file
    manifest_file = Path(build_directory.name).joinpath(
        arrangement["collection_id"],
        archival_object["component_id"],
        "manifest.json",
    )
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_file, "w") as f:
        f.write(json.dumps(manifest, indent=4))
    logger.debug(f"🐞 MANIFEST FILE GENERATED: {manifest_file}")


def calculate_pyramid_pages(
    width: int, height: int, tile_size: int = PYRAMID_TILE_SIZE
) -> int:
    """Calculate the number of pyramid levels vips will generate for an
    image of the given dimensions and tile size (serverless-iiif's "pages")."""
    return max(
        1, math.ceil(math.log(max(width, height) / tile_size, 2)) + 1
    )


def create_pyramid_tiff(
    build_directory: tempfile.TemporaryDirectory[str],
    filepath: Path,
    archival_object: dict,
    arrangement: dict,
    sequence_indicator: str,
) -> None:
    try:
        # NOTE vips has problems with JP2 source images
        magick_identify = subprocess.run(
            [
                config("MAGICK_CMD"),
                "identify",
                "-format",
                "%m*%w*%h",
                filepath.as_posix(),
            ],
            capture_output=True,
            check=True,
            text=True,
        )
        image_format, image_width, image_height = magick_identify.stdout.strip().split(
            "*"
        )
        image_width, image_height = int(image_width), int(image_height)

        if image_format == "JP2":
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
                arrangement["collection_id"],
                archival_object["component_id"],
                f"{sequence_indicator}.ptif",
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
                str(PYRAMID_TILE_SIZE),
                "--tile-height",
                str(PYRAMID_TILE_SIZE),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.debug(f"🐞 PYRAMID TIFF CREATED: {pyramid_tiff_file}")
        pyramid_tiff_metadata_file = f"{pyramid_tiff_file}.metadata.json"
        with open(pyramid_tiff_metadata_file, "w") as f:
            json.dump(
                {
                    "width": image_width,
                    "height": image_height,
                    "pages": calculate_pyramid_pages(image_width, image_height),
                    "tilesize": PYRAMID_TILE_SIZE,
                },
                f,
            )
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
    sequence_indicator: str,
) -> None:
    type, encoding = mimetypes.guess_type(filepath.as_posix())

    if not type:
        logger.error("❌ UNKNOWN MIME TYPE: %s", filepath.name)
        return

    if type.startswith("image/"):
        create_pyramid_tiff(
            build_directory, filepath, archival_object, arrangement, sequence_indicator
        )
    elif type.startswith("video/"):
        video_key = "/".join(
            [
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
    sequenced_filepaths: dict[str, Path],
) -> None:
    """Concurrently process files in the filepaths list."""
    with ProcessPoolExecutor(
        initializer=_worker_init, initargs=(str(settings_path),)
    ) as executor:
        [
            executor.submit(
                conditional_derivative_file_processing,
                build_directory,
                filepath,
                archival_object,
                arrangement,
                sequence_indicator,
            )
            # for filepath in filepaths
            for sequence_indicator, filepath in sequenced_filepaths.items()
        ]


def archival_object_level_processing(
    build_directory: tempfile.TemporaryDirectory[str],
    filepaths: list[Path],
    archival_object: dict,
    arrangement: dict,
    sequenced_filepaths: dict[str, Path],
) -> None:
    logger.debug(f"🐞 {archival_object['component_id']}")
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
        build_directory,
        filepaths,
        archival_object,
        arrangement,
        mimetype,
        sequenced_filepaths,
    )
    if filepaths:
        loop_over_archival_object_files(
            build_directory,
            filepaths,
            archival_object,
            arrangement,
            sequenced_filepaths,
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
    last = components[-1]
    # Use tuple form of endswith to check for either suffix in one call
    if last.endswith(("r", "v")):
        digits, rv = last[:-1], last[-1]
    else:
        digits, rv = last, None
    if not digits.isdigit():
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


def update_external_ark_url(archival_object: dict) -> None:
    """POST updated archival_object if external_ark_url has changed."""
    archivesspace_archival_object = cascflow.archivesspace_get(
        archival_object["uri"]
    ).json()
    if archival_object.get("external_ark_url") != archivesspace_archival_object.get(
        "external_ark_url"
    ):
        logger.info(
            "✨ UPDATE external_ark_url VALUE IN %s FROM %s TO %s",
            archival_object.get("component_id", ""),
            archivesspace_archival_object.get("external_ark_url", ""),
            archival_object.get("external_ark_url", ""),
        )
        cascflow.archivesspace_post(archival_object["uri"], archival_object)
    return


def get_our_ark(archival_object: dict) -> str:
    # validate, update, or mint ARK as needed
    naan = config("OUR_NAAN")
    s3_client = cascflow.establish_s3_connection()
    if s3_client is None:
        raise RuntimeError("Failed to establish S3 connection")

    existing_our_ark = arkminter.get_existing_our_ark(archival_object, naan)
    if existing_our_ark:
        metadata = json.loads(
            arkminter.format_metadata(
                nma=config("OUR_NMA"),
                ark=existing_our_ark,
                title=archival_object["title"],
                creator="; ".join(
                    format_archival_object_creators_display(archival_object).values()
                )
                or "",
                date="; ".join(format_archival_object_dates_display(archival_object))
                or "",
            )
        )
        arkminter.put_objects(
            bucket_name=config("RESOLVER_BUCKET"),
            ark=existing_our_ark,
            redirect_location=f"{config('ALCHEMIST_BASE_URL').rstrip('/')}/{existing_our_ark}",
            metadata=metadata,
            s3_client=s3_client,
        )
        our_ark = existing_our_ark
    else:
        minted_ark = arkminter.mint_ark(
            bucket_name=config("RESOLVER_BUCKET"),
            redirect_domain=config("ALCHEMIST_BASE_URL"),
            nma=config("OUR_NMA"),
            naan=naan,
            title=archival_object["title"],
            creator="; ".join(
                format_archival_object_creators_display(archival_object).values()
            )
            or "",
            date="; ".join(format_archival_object_dates_display(archival_object)) or "",
            shoulder=config("OUR_SHOULDER", default=""),
            s3_client=s3_client,
        )
        our_ark = minted_ark
    return our_ark


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


def validate_settings_for_publication(settings_validation_results: dict) -> None:
    missing = settings_validation_results.get("missing", [])
    invalid = settings_validation_results.get("invalid", [])
    if missing:
        message = "❌ REQUIRED SETTINGS NOT SET"
        logger.error(message)
        for setting in missing:
            logger.error(f"❌ {setting['key']}: {setting['detail']}")
    if invalid:
        message = "❌ INVALID SETTINGS VALUES"
        logger.error(message)
        for setting in invalid:
            logger.error(f"❌ {setting['key']}: {setting['detail']}")
    if missing or invalid:
        raise RuntimeError("❌ SETTINGS VALIDATION FAILED")
    logger.debug("✅ ALL REQUIRED SETTINGS ARE SET AND USABLE")


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
    missing_sequence_indicators = []
    sequence_indicators = {}
    # get the eligible archival object data from validation_results
    eligible_archival_objects_by_id = validation_results.get("eligible_archival_objects", {})
    if eligible_archival_objects_by_id:
        logger.info(
            f"{next(iter(eligible_archival_objects_by_id))}{', …' if len(eligible_archival_objects_by_id) > 1 else ''}"
        )
    ## iterate over the first level of entries in the source directory
    for entry in source_path.iterdir():
        ## validate the entry (file or directory) using cached data
        if entry.stem in eligible_archival_objects_by_id:
            archival_object = eligible_archival_objects_by_id[entry.stem]
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
            logger.debug(
                f"🐞 SEQUENCE_INDICATORS for {entry.stem}: {sequence_indicators[entry.stem]}"
            )
    ## validation and messaging
    if eligible_archival_objects:
        for eligible_archival_object in eligible_archival_objects:
            logger.info(f"🉑 {eligible_archival_object}")
            if sequence_indicators.get(eligible_archival_object) is False:
                missing_sequence_indicators.append(eligible_archival_object)
        logger.info(f"🗂 ARCHIVAL OBJECT COUNT: {len(eligible_archival_objects)}")
        logger.info(f"📄 FILE COUNT: {file_count}")
    if file_count == 0:
        message = "❌ NO FILES FOUND"
        logger.error(message)
        raise FileNotFoundError(message)
    if missing_sequence_indicators:
        message = "❌ NO VALID SEQUENCE INDICATORS FOUND IN FILE NAMES FOR: {}".format(
            ", ".join(missing_sequence_indicators)
        )
        logger.error(message)
        raise RuntimeError(message)
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
    global args, settings_path, config, logger
    args = parser.parse_args()

    # set up settings path and logging
    settings_path = (
        Path(args.settings).expanduser().resolve()
        if args.settings
        else Path(__file__).parent.joinpath("settings.ini").resolve()
    )
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
        settings_validation_results = cascflow.validate_settings(ALCHEMIST_SETTINGS_SPEC)
        validate_settings_for_publication(settings_validation_results)
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
                our_ark = get_our_ark(archival_object)
                archival_object["external_ark_url"] = (
                    f"https://{config('OUR_NMA')}/{our_ark}"
                )
                arrangement = cascflow.get_arrangement(archival_object)
                filepaths = []
                sequenced_filepaths = {}
                archival_object_level_processing(
                    build_directory,
                    filepaths,
                    archival_object,
                    arrangement,
                    sequenced_filepaths,
                )
                publish_archival_object_access_files(
                    build_directory, archival_object, arrangement
                )
                update_digital_object_metadata(archival_object)
                if validation_results.get("identifier_level") == "archival_object":
                    # Invalidate the paths for the updated metadata.
                    if config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID", default=False):
                        # We should only have a single archival object.
                        if arrangement is not None:
                            invalidate_cloudfront_paths(paths=[f"/{our_ark}/*"])
            # TODO rethink the circumstance of updating metadata for a resource-level identifier.
            # This whole branch is currently dead: cascflow.validate_metadata_identifier()
            # is never called with target="metadata" above, so identifier_level can never
            # come back "resource" and a collection identifier is silently treated as a
            # single (nonexistent) archival object instead of expanding to its members.
            # Before wiring this back up, rethink from scratch:
            #   - Alchemist page paths are now independent per object (/ark:NAAN/name),
            #     not nested under a shared resource path segment, so the wildcard
            #     invalidation below (f"/{args.context}/*") can never match anything real
            #     and per-object invalidation would be needed for every member instead.
            #   - get_s3_resource_archival_object_paths() (and COMMON_PATH_PREFIX) discovers
            #     a resource's "published" archival objects by walking an S3 key prefix
            #     scheme built around the old path pattern. Under the new ARK-based
            #     paradigm this whole discovery mechanism, and COMMON_PATH_PREFIX itself,
            #     may no longer be the right approach and could become obsolete.
            #   - Decide whether external_ark_url should also be persisted back to
            #     ArchivesSpace here (via update_external_ark_url), as the publication/files
            #     pipeline already does, once per-object handling is sorted out.
            if validation_results.get("identifier_level") == "resource":
                if config("ALCHEMIST_CLOUDFRONT_DISTRIBUTION_ID", default=False):
                    # Invalidate everything under the resource path component.
                    invalidate_cloudfront_paths(paths=[f"/{args.context}/*"])
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
                """process each archival_object result as it is yielded"""
                logger.debug(f"🐞 STAGE_2_PATH_OBJ: {stage_2_path_obj}")
                our_ark = get_our_ark(archival_object)
                logger.debug(f"🐞 OUR_ARK: {our_ark}")
                archival_object["external_ark_url"] = (
                    f"https://{config('OUR_NMA')}/{our_ark}"
                )
                logger.debug(
                    f"🐞 ARCHIVAL_OBJECT[EXTERNAL_ARK_URL]: {archival_object['external_ark_url']}"
                )
                sequenced_filepaths = {
                    get_sequence_indicator(path): path
                    for path in sorted(filepaths, key=get_sequence_indicator)
                }
                if Path(stage_2_path_obj).is_file():
                    # when the object is a single file reset the sequence indicator to "0001"
                    sequenced_filepaths = {"0001": filepaths[0]}
                logger.debug(f"🐞 SEQUENCED_FILEPATHS: {sequenced_filepaths}")
                archival_object_level_processing(
                    build_directory,
                    filepaths,
                    archival_object,
                    arrangement,
                    sequenced_filepaths,
                )
                publish_archival_object_access_files(
                    build_directory, archival_object, arrangement
                )
                create_digital_object_file_versions(
                    build_directory,
                    filepaths,
                    archival_object,
                    arrangement,
                    sequenced_filepaths,
                )
                update_external_ark_url(archival_object)
                cascflow.move_to_stage_3(stage_2_path_obj, batch_directory)
                if args.target == "files":
                    # Invalidate the paths for the updated files.
                    cloudfront_invalidation_batch.append(
                        "/".join(
                            [
                                "",  # empty to start with a leading slash
                                our_ark,
                                "*",  # end with a wildcard
                            ]
                        )
                    )
            if args.target == "files" and cloudfront_invalidation_batch:
                invalidate_cloudfront_paths(paths=cloudfront_invalidation_batch)
                for path in cloudfront_invalidation_batch:
                    # prepend /iiif/2 to each path
                    cloudfront_invalidation_batch[
                        cloudfront_invalidation_batch.index(path)
                    ] = f"/iiif/2{path}"
                invalidate_cloudfront_paths(
                    distribution=config("IIIF_CLOUDFRONT_DISTRIBUTION_ID"),
                    paths=cloudfront_invalidation_batch,
                )
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except Exception as exception:
        logger.error(f"❌ UNEXPECTED ERROR: {exception}")
        raise
