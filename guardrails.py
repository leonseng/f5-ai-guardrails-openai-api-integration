from collections import namedtuple
import json
import logging
from typing import Dict, Any, Optional

import httpx

logger = logging.getLogger("uvicorn.error")

GuardrailsScanResult = namedtuple("GuardrailsScanResult", ["outcome", "output"])


class GuardrailsClient():
    def __init__(self, api_url: str, api_token: str, project_id: str, timeout: float = 30.0):
        self.api_url = api_url
        self.api_token = api_token
        self.project_id = project_id
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def scan(
        self,
        input_text: str,
        force_enabled: Optional[list] = [],
        external_metadata: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
        timeout: float = 30.0,
    ) -> GuardrailsScanResult:
        payload = {
            "externalMetadata": external_metadata,
            "forceEnabled": force_enabled,
            "input": input_text,
            "project": self.project_id,
            "verbose": verbose,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.api_url.rstrip('/')}/scans", headers=self.headers, json=payload)

        output = input_text
        try:
            resp.raise_for_status()
            scan_resp_body = resp.json()
            scan_outcome = scan_resp_body["result"]["outcome"]
            logger.debug(f"Guardrail scan results: {scan_outcome}.")

            if scan_outcome not in ["cleared", "flagged", "redacted"]:
                raise ValueError(
                    f"Unknown Guardrail scan outcome: {scan_outcome}")

            if scan_outcome == "redacted":
                output = scan_resp_body["redactedInput"]

        except json.JSONDecodeError as e:
            # fail open
            logger.error("Guardrail scan response is not valid JSON")
            raise e
        except httpx.HTTPStatusError as e:
            # fail open
            logger.error(f"Guardrail scan failed: {e}")
            raise e

        return GuardrailsScanResult(scan_resp_body["result"]["outcome"], output)
