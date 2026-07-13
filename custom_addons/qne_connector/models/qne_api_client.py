# -*- coding: utf-8 -*-
"""
Thin HTTP client around the QNE REST API.

IMPORTANT: QNE does not have one single public API spec - endpoint paths,
query params and the exact JSON field names below (SUPPLIER_FIELD_MAP)
depend on which QNE product/version you are licensed for (QNE Optimum /
QNE AI Cloud Accounting, etc). The paths and field names used here are
placeholders following common QNE API naming conventions - adjust the
constants marked with TODO to match the actual endpoint your account
gives you access to (check the Swagger/API doc your QNE reseller
provides, e.g. something like https://<your-tenant>-api.qne.cloud/doc).
"""

import logging

import requests

_logger = logging.getLogger(__name__)

# TODO: confirm actual path with your QNE API documentation
SUPPLIER_LIST_ENDPOINT = "/api/suppliers"

DEFAULT_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 100


class QNEAPIError(Exception):
    """Raised for any non-2xx response or connectivity failure."""


class QNEAPIClient:
    """Lightweight wrapper - keeps HTTP concerns out of the Odoo models."""

    def __init__(self, base_url, api_key, timeout=DEFAULT_TIMEOUT):
        if not base_url:
            raise QNEAPIError("QNE API base URL is not configured.")
        if not api_key:
            raise QNEAPIError("QNE API key is not configured.")
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self):
        return {
            # TODO: adjust header name to whatever QNE expects
            # (commonly "X-API-KEY", "Authorization: Apikey <key>", etc.)
            "DbCode": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(
                url, headers=self._headers(), params=params, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            _logger.exception("QNE API connection error calling %s", url)
            raise QNEAPIError(f"Could not reach QNE API at {url}: {exc}") from exc

        if response.status_code == 401:
            raise QNEAPIError("QNE API rejected the API key (401 Unauthorized).")
        if not response.ok:
            raise QNEAPIError(
                f"QNE API returned {response.status_code} for {url}: {response.text[:500]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise QNEAPIError(f"QNE API returned non-JSON response from {url}") from exc

    def fetch_suppliers(self, page_size=DEFAULT_PAGE_SIZE, updated_since=None):
        """Generator yielding supplier dicts, transparently paging through results.

        TODO: adjust the query param names (page/limit/updatedSince) and the
        response envelope keys ("data" / "items" / "total") to match your
        QNE API's actual pagination scheme.
        """
        page = 1
        while True:
            params = {"page": page, "limit": page_size}
            if updated_since:
                params["updatedSince"] = updated_since

            payload = self._get(SUPPLIER_LIST_ENDPOINT, params=params)

            # Handle a couple of common envelope shapes defensively.
            if isinstance(payload, list):
                records = payload
                has_more = len(records) == page_size
            else:
                records = payload.get("data") or payload.get("items") or []
                total = payload.get("total")
                has_more = (
                    (total is not None and page * page_size < total)
                    or len(records) == page_size
                )

            if not records:
                break

            for record in records:
                yield record

            if not has_more:
                break
            page += 1
