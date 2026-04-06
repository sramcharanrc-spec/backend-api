import boto3



textract = boto3.client("textract", region_name="us-east-1")


def analyze_document(bucket, key):

    print("📄 Textract Input →", bucket, key)

    response = textract.analyze_document(
        Document={
            "S3Object": {
                "Bucket": bucket,
                "Name": key
            }
        },
        FeatureTypes=["FORMS", "TABLES"]
    )

    return response