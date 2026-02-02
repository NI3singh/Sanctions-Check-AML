"""
Yente API client for sanctions matching
Handles all communication with the Yente service
"""
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from config import settings
from models import PersonScreeningRequest, MatchedEntity
from utils.audit_logger import audit_logger


class YenteClient:
    """Client for Yente sanctions matching service"""
    
    def __init__(self):
        self.base_url = settings.YENTE_BASE_URL.rstrip("/")
        self.timeout = httpx.Timeout(
            timeout=settings.YENTE_TIMEOUT,
            connect=settings.YENTE_CONNECT_TIMEOUT
        )
    
    async def check_health(self) -> Tuple[bool, str]:
        """Check if Yente service is ready"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/readyz")
                
                if response.status_code == 200:
                    return True, "ok"
                else:
                    return False, f"Yente returned status {response.status_code}"
        
        except httpx.TimeoutException:
            return False, "Yente service timeout"
        except httpx.ConnectError:
            return False, "Cannot connect to Yente service"
        except Exception as e:
            return False, f"Yente health check failed: {str(e)}"
    
    def _build_yente_query(self, request: PersonScreeningRequest) -> Dict[str, Any]:
        """
        Build Yente query payload from screening request
        
        Strategy:
        - Always include name (required)
        - Add optional fields (country, DOB, IDs) to improve matching accuracy
        - Yente uses these fields for weighted scoring
        """
        properties: Dict[str, List[Any]] = {
            "name": [request.full_name]
        }
        
        # Add country for geographic context
        if request.country:
            properties["country"] = [request.country]
        
        # Add date of birth for stronger identity confirmation
        if request.date_of_birth:
            properties["birthDate"] = [request.date_of_birth]
        
        # Add passport number (strong identifier)
        if request.passport_number:
            properties["passportNumber"] = [request.passport_number]
        
        # Add national ID (weaker but useful signal)
        if request.national_id:
            properties["idNumber"] = [request.national_id]
        
        return {
            "queries": {
                "q1": {
                    "schema": "Person",
                    "properties": properties
                }
            }
        }
    
    def _extract_entity_properties(self, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract essential properties from Yente entity response"""
        props = entity_data.get("properties", {}) or {}
        
        # Extract all name variants
        names = []
        if "name" in props:
            names.extend(props["name"])
        if "alias" in props:
            names.extend(props["alias"])
        names = list(set(names))  # Deduplicate
        
        # Extract countries
        countries = props.get("country", []) or []
        
        # Extract birth dates
        birth_dates = props.get("birthDate", []) or []
        
        # Extract sanctions programs
        programs = props.get("program", []) or []
        
        # Extract source URLs
        source_urls = props.get("sourceUrl", []) or []
        
        return {
            "names": names,
            "countries": countries,
            "birth_dates": birth_dates,
            "programs": programs,
            "source_urls": source_urls
        }
    
    async def screen_against_dataset(
        self,
        request: PersonScreeningRequest,
        dataset: str,
        request_id: str
    ) -> List[MatchedEntity]:
        """
        Screen person against a specific sanctions dataset
        
        Returns:
            List of matched entities with scores
        """
        query_payload = self._build_yente_query(request)
        matches: List[MatchedEntity] = []
        
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/match/{dataset}",
                    json=query_payload
                )
                
                response_time_ms = (time.time() - start_time) * 1000
                
                # Log the query
                audit_logger.log_yente_query(
                    request_id=request_id,
                    dataset=dataset,
                    query_payload=query_payload,
                    response_status=response.status_code,
                    response_time_ms=response_time_ms
                )
                
                if response.status_code != 200:
                    audit_logger.log_error(
                        request_id=request_id,
                        error_type="yente_api_error",
                        error_message=f"Status {response.status_code}: {response.text}",
                        dataset=dataset
                    )
                    return matches
                
                # Parse response
                data = response.json()
                results = data.get("responses", {}).get("q1", {}).get("results", []) or []
                
                # Convert to MatchedEntity objects
                for result in results:
                    entity_props = self._extract_entity_properties(result)
                    
                    match_entity = MatchedEntity(
                        entity_id=result.get("id", ""),
                        dataset=dataset,
                        caption=result.get("caption", ""),
                        score=float(result.get("score", 0.0)),
                        match=bool(result.get("match", False)),
                        **entity_props
                    )
                    matches.append(match_entity)
                
                # Log match results
                if matches:
                    top_match = max(matches, key=lambda m: m.score)
                    audit_logger.log_matches_found(
                        request_id=request_id,
                        dataset=dataset,
                        match_count=len(matches),
                        top_score=top_match.score,
                        top_entity_id=top_match.entity_id
                    )
                else:
                    audit_logger.log_matches_found(
                        request_id=request_id,
                        dataset=dataset,
                        match_count=0,
                        top_score=0.0
                    )
                
                return matches
        
        except httpx.TimeoutException:
            audit_logger.log_error(
                request_id=request_id,
                error_type="yente_timeout",
                error_message=f"Timeout querying {dataset}",
                dataset=dataset
            )
            return matches
        
        except Exception as e:
            audit_logger.log_error(
                request_id=request_id,
                error_type="yente_exception",
                error_message=str(e),
                dataset=dataset
            )
            return matches
    
    async def screen_all_datasets(
        self,
        request: PersonScreeningRequest,
        request_id: str
    ) -> List[MatchedEntity]:
        """
        Screen person against all configured datasets
        
        Returns:
            Combined list of all matches across datasets
        """
        all_matches: List[MatchedEntity] = []
        
        for dataset in settings.DATASETS:
            dataset_matches = await self.screen_against_dataset(
                request=request,
                dataset=dataset,
                request_id=request_id
            )
            all_matches.extend(dataset_matches)
        
        # Sort by score (descending)
        all_matches.sort(key=lambda m: m.score, reverse=True)
        
        return all_matches


# Global Yente client instance
yente_client = YenteClient()