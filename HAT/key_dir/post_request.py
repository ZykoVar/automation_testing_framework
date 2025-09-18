import allure

from HAT.core.global_context import GlobalContext


class PostRequest:
    def __init__(self, request):
        self.request = request

    @allure.step("post_request")
    def post_request(self, **kwargs):
        # self.show_log("post_request", kwargs)
        request_data = {
            "url": kwargs.get("request_url", None),
            "params": kwargs.get("request_parameters", None),
            "files": kwargs.get("file_path", None),
            "headers": kwargs.get("request_headers", None)
        }
        content_type = kwargs.get("content_type", "data").lower()
        if content_type == "json":
            request_data["json"] = kwargs.get("request_payload", None)
        elif content_type == "data":
            request_data["data"] = kwargs.get("request_payload", None)
        else:
            raise Exception("Content type error")

        response = self.request.request("post", **request_data)
        GlobalContext().set_context("response", response)
        # self.show_log("response_data", response.json())
