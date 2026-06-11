import asyncio
from intake.s3_service import upload_to_s3
from intake.processor import ProcessorFactory
from intake.claim_mapper import map_to_claim_schema
from intake.claim_store import store_claim_data
from intake.service_extractor import extract_services
from utils.logger import log_event
from utils.retry import retry_wrapper


class UniversalIntake:

    async def process(self, file, s3_url):

        file_type = self.detect_type(file.filename)

        if file_type == "document":
            raw_data = await DocumentProcessor().process(s3_url)

        elif file_type == "tabular":
            raw_data = await TabularProcessor().process(s3_url)

        else:
            raise Exception("Unsupported format")

        # 🔥 TEMPLATE DETECTION
        template = TemplateDetector().detect(raw_data)

        # 🔥 CONFIDENCE CHECK
        if template["confidence"] < 0.7:
            return {
                "status": "HITL_REQUIRED",
                "reason": "Low template confidence",
                "template": template
            }

        return {
            "status": "READY",
            "data": raw_data,
            "template": template
        }