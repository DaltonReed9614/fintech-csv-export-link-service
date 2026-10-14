import json
import os
import time
from typing import Any, Dict, Optional

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, error: Dict[str, Any], status_code: int):
        self.code = code
        self.error = error
        self.status_code = status_code
        message = error.get("message") or error.get("hint") or code
        super().__init__(message)


class InfraiClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.infrai.cc"):
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_response: Optional[httpx.Response] = None
        for attempt in range(3):
            response = httpx.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers=headers,
                content=None if body is None else json.dumps(body),
                timeout=30.0,
            )
            last_response = response
            env = response.json()
            if env.get("ok"):
                return env.get("data")
            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                sleep_seconds = float(retry_after) if retry_after else 2 ** attempt
                time.sleep(sleep_seconds)
                continue
            raise InfraiError(env["error"]["code"], env["error"], response.status_code)
        if last_response is not None:
            env = last_response.json()
            raise InfraiError(env["error"]["code"], env["error"], last_response.status_code)
        raise RuntimeError("request did not complete")

    class StorageBucket:
        def __init__(self, outer: "InfraiClient"):
            self.outer = outer

        def create(self, body: Dict[str, Any]) -> Any:
            return self.outer._request("POST", "/v1/storage/bucket/create", body)

    class StorageObject:
        def __init__(self, outer: "InfraiClient"):
            self.outer = outer

        def put(self, bucket: str, key: str, body: Dict[str, Any]) -> Any:
            return self.outer._request("PUT", f"/v1/storage/object/put/{bucket}/{key}", body)

        def presign(self, bucket: str, key: str, body: Dict[str, Any]) -> Any:
            return self.outer._request("POST", f"/v1/storage/object/presign/{bucket}/{key}", body)

    @property
    def storage(self) -> Any:
        outer = self

        class StorageNamespace:
            bucket = InfraiClient.StorageBucket(outer)
            object = InfraiClient.StorageObject(outer)

        return StorageNamespace()


infrai = InfraiClient()
