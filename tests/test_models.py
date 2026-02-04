class TestModelsEndpoint:
    """Test models endpoint functionality"""
    
    def test_models_listing_mock(
        self, client, mock_backend, setup_mock_models
    ):
        """Test models listing with mock backend"""
        setup_mock_models(models=["gpt-4o-mini", "gpt-4o"])
        
        response = client.get("/v1/models")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        model_ids = [model["id"] for model in data["data"]]
        assert "gpt-4o-mini" in model_ids
        assert "gpt-4o" in model_ids
    
    def test_models_backend_error(self, client, mock_backend, test_env_vars):
        """Test handling of backend errors for models endpoint"""
        from httpx import Response
        
        mock_backend.get("/v1/models").mock(
            return_value=Response(status_code=500, content=b"Internal Server Error")
        )
        
        response = client.get("/v1/models")
        
        assert response.status_code == 500
