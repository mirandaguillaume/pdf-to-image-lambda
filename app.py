import boto3
import logging
import os

from chalice import Chalice, Response
from io import BytesIO
from pdf2image import convert_from_bytes

app = Chalice(app_name='pdf2image')
app.log.setLevel(logging.DEBUG)


DPI = 300
if 'DPI' in os.environ:
    try:
        DPI = int(os.environ['DPI'])
    except Exception as e:
        app.log.debug(f"Couldn't process DPI environment variable: {str(e)}.  Using the default: DPI=300")
else:
    app.log.info(f"No DPI environment variable set.  Using the default: DPI=300")

_SUPPORTED_IMAGE_EXTENSIONS = ["ppm", "jpeg", "png", "tiff"]
FMT = "png"
if 'FMT' in os.environ:
    environ_fmt = str(os.environ['FMT'])
    if environ_fmt in _SUPPORTED_IMAGE_EXTENSIONS:
        FMT = environ_fmt
    else:
        app.log.debug(f"Couldn't process FMT variable.  "
                      f"Only the following formats are supported: {','.join(_SUPPORTED_IMAGE_EXTENSIONS)}.  "
                      f"Using the default: FMI='png'")
else:
    app.log.info(f"No FMT environment variable set.  Using the default: FMT='png'")

ORIGIN_BUCKET = ''
if 'ORIGIN_BUCKET' in os.environ:
    ORIGIN_BUCKET = str(os.environ['ORIGIN_BUCKET'])
    app.log.info(f"Setting the origin bucket: {ORIGIN_BUCKET}. "
                 f"Be sure to set the S3 bucket trigger on the Lambda's configuration")
else:
    app.log.info(f"Couldn't process the ORIGIN_BUCKET environment variable. "
                 f"Be sure to set the S3 bucket trigger on the Lambda's configuration.")

_SUPPORTED_FILE_EXTENSION = '.pdf'


@app.on_s3_event(bucket=ORIGIN_BUCKET,
                 events=['s3:ObjectCreated:*'])
def pdf_to_image(event):
    """Take a pdf fom an S3 bucket and convert it to a list of pillow images (one for each page of the pdf).
    :param event: A Lambda event (referring to an S3 event object created event).
    :return:
    """
    if not event.key.endswith(_SUPPORTED_FILE_EXTENSION):
        raise Exception(f"Only .pdf files are supported by this module.")

    app.log.info(f"Fetching item (bucket: '{event.bucket}', key: '{event.key}') from S3.")

    # Fetch the image bytes
    s3 = boto3.resource('s3')
    obj = s3.Object(event.bucket, event.key)
    infile = obj.get()['Body'].read()
    app.log.info("Successfully retrieved S3 object.")

    images = convert_from_bytes(infile,
                                dpi=DPI,
                                fmt=FMT)
    app.log.info("Successfully converted pdf to image.")

    for page_num, image in enumerate(images):

        split_event_key = event.key.split('/')

        filename = split_event_key.pop()

        split_event_key.pop(0)

        directory = 'output/' + '/'.join(split_event_key)

        # Then save the image and name it: <name of the pdf>-page<page number>.FMT
        location = directory + "/" + str(page_num) + '.' + FMT

        app.log.info(f"Saving page number {str(page_num)} to S3 at location: {ORIGIN_BUCKET}, {location}.")

        # Load it into the buffer and save the boytjie to S3
        buffer = BytesIO()
        image.save(buffer, FMT.upper())
        buffer.seek(0)
        s3.Object(
            ORIGIN_BUCKET,
            location
        ).put(
            Body=buffer,
            Metadata={
                'ORIGINAL_DOCUMENT_BUCKET': event.bucket,
                'ORIGINAL_DOCUMENT_KEY': event.key,
                'PAGE_NUMBER': str(page_num),
                'PAGE_COUNT': str(len(images))
            }
        )

    return Response(f"PDF document ({event.key}) successfully converted to a series of images.")
