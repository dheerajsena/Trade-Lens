class BrokerClient:
    def __init__(self, api_key:str="", api_secret:str="", access_token:str=""):
        self.api_key = api_key; self.api_secret = api_secret; self.access_token = access_token
    def is_configured(self)->bool:
        return bool(self.api_key and self.api_secret and self.access_token)
    def place_order(self, symbol:str, qty:int, side:str, price:float=None, order_type:str="MARKET"):
        return {"ok": True, "mock": True}
