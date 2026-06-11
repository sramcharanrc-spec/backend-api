class DocumentProcessor:

    def __init__(self):
        self.textract = TextractService()

    async def process(self, s3_url):

        result = await self.textract.extract(s3_url)

        key_values = self.extract_kv(result)
        tables = self.extract_tables(result)

        return {
            "type": "document",
            "fields": key_values,
            "tables": tables
        }