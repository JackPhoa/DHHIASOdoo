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

# TODO: confirm actual paths with your QNE API documentation - these follow
# common QNE REST naming conventions but your tenant may differ.
SUPPLIER_LIST_ENDPOINT = "/api/suppliers"
SUPPLIER_DETAIL_ENDPOINT = "/api/suppliers/{id}"
CUSTOMER_LIST_ENDPOINT = "/api/customers"
CUSTOMER_DETAIL_ENDPOINT = "/api/customers/{id}"
SALES_INVOICE_LIST_ENDPOINT = "/api/salesinvoices"
SALES_INVOICE_DETAIL_ENDPOINT = "/api/salesinvoices/{id}"
PURCHASE_INVOICE_LIST_ENDPOINT = "/api/purchaseinvoices"
PURCHASE_INVOICE_DETAIL_ENDPOINT = "/api/purchaseinvoices/{id}"
STOCK_ITEM_LIST_ENDPOINT = "/api/stocks"
STOCK_ITEM_DETAIL_ENDPOINT = "/api/stocks/{id}"
PURCHASE_ORDER_LIST_ENDPOINT = "/api/purchaseorders"
PURCHASE_ORDER_DETAIL_ENDPOINT = "/api/purchaseorders/{id}"
DELIVERY_ORDER_LIST_ENDPOINT = "/api/deliveryorders"
DELIVERY_ORDER_DETAIL_ENDPOINT = "/api/deliveryorders/{id}"

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

    def _post(self, path, payload):
        url = f"{self.base_url}{path}"
        try:
            response = requests.post(
                url, headers=self._headers(), json=payload, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            _logger.exception("QNE API connection error calling %s", url)
            raise QNEAPIError(f"Could not reach QNE API at {url}: {exc}") from exc
        return self._handle_response(response, url)

    def _put(self, path, payload):
        url = f"{self.base_url}{path}"
        try:
            response = requests.put(
                url, headers=self._headers(), json=payload, timeout=self.timeout
            )
        except requests.exceptions.RequestException as exc:
            _logger.exception("QNE API connection error calling %s", url)
            raise QNEAPIError(f"Could not reach QNE API at {url}: {exc}") from exc
        return self._handle_response(response, url)

    def _handle_response(self, response, url):
        if response.status_code == 401:
            raise QNEAPIError("QNE API rejected the API key (401 Unauthorized).")
        if not response.ok:
            raise QNEAPIError(
                f"QNE API returned {response.status_code} for {url}: {response.text[:500]}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise QNEAPIError(f"QNE API returned non-JSON response from {url}") from exc

    # ------------------------------------------------------------------
    # Outbound: push Odoo records to QNE (create/update)
    # ------------------------------------------------------------------
    def create_supplier(self, payload):
        return self._post(SUPPLIER_LIST_ENDPOINT, payload)

    def update_supplier(self, qne_id, payload):
        return self._put(SUPPLIER_DETAIL_ENDPOINT.format(id=qne_id), payload)

    def create_customer(self, payload):
        return self._post(CUSTOMER_LIST_ENDPOINT, payload)

    def update_customer(self, qne_id, payload):
        return self._put(CUSTOMER_DETAIL_ENDPOINT.format(id=qne_id), payload)

    def create_sales_invoice(self, payload):
        return self._post(SALES_INVOICE_LIST_ENDPOINT, payload)

    def update_sales_invoice(self, qne_id, payload):
        return self._put(SALES_INVOICE_DETAIL_ENDPOINT.format(id=qne_id), payload)

    def create_purchase_invoice(self, payload):
        return self._post(PURCHASE_INVOICE_LIST_ENDPOINT, payload)

    def update_purchase_invoice(self, qne_id, payload):
        return self._put(PURCHASE_INVOICE_DETAIL_ENDPOINT.format(id=qne_id), payload)

    def create_stock_item(self, payload):
        return self._post(STOCK_ITEM_LIST_ENDPOINT, payload)

    def update_stock_item(self, qne_id, payload):
        return self._put(STOCK_ITEM_DETAIL_ENDPOINT.format(id=qne_id), payload)

    def create_purchase_order(self, payload):
        return self._post(PURCHASE_ORDER_LIST_ENDPOINT, payload)

    def update_purchase_order(self, qne_id, payload):
        return self._put(PURCHASE_ORDER_DETAIL_ENDPOINT.format(id=qne_id), payload)

    def create_delivery_order(self, payload):
        return self._post(DELIVERY_ORDER_LIST_ENDPOINT, payload)

    def update_delivery_order(self, qne_id, payload):
        return self._put(DELIVERY_ORDER_DETAIL_ENDPOINT.format(id=qne_id), payload)

    # ------------------------------------------------------------------
    # Inbound: pull records from QNE
    # ------------------------------------------------------------------
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
