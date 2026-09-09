# Proposed Provenance Labeling Fixes (Diff)

## 1. schemas.py: Add `data_source` field
```diff
--- backend/app/schemas.py
+++ backend/app/schemas.py
@@ -28,6 +28,7 @@
     source_file: Optional[str] = None
     ingestion_ts: Optional[str] = None      # Time the snapshot was retrieved (download_time)
     is_real: bool = False                   # Flag for Copernicus vs Synthetic
+    data_source: Literal["real", "cached", "synthetic", "unavailable"] = "cached"
     data_status: Literal["REAL DATA", "CACHED REAL DATA", "DEMONSTRATION DATA"] = "CACHED REAL DATA"
     source_organization: Optional[str] = "INCOIS / Copernicus Marine"
     product_id: Optional[str] = None
@@ -48,6 +49,7 @@
     source_url: Optional[str] = None
     last_updated: Optional[str] = None
     kind: RecordKind
+    data_source: Literal["real", "cached", "synthetic", "unavailable"] = "cached"
     data_status: Literal["REAL DATA", "CACHED REAL DATA", "DEMONSTRATION DATA"] = "CACHED REAL DATA"
     source_organization: Optional[str] = "INCOIS / Copernicus Marine"
```

## 2. adapters.py: Fix ArgoGliderAdapter (Point 1)
```diff
--- backend/app/adapters.py
+++ backend/app/adapters.py
@@ -423,8 +423,8 @@
                     variable="temperature", latitude=lat, longitude=lon, depth=0,
                     time=_time_at(0), value=25.0, unit="degC",
                     platform_id=pid, platform_type="argo",
-                    data_status="CACHED REAL DATA",
-                    source_organization="Argo GDAC / Argovis"
+                    data_source="synthetic",
+                    source_organization="Argo GDAC / Argovis (Demo)"
                 ))
         return records
```

## 3. adapters.py: Fix `_generate_synthetic_observations` (Point 2)
```diff
--- backend/app/adapters.py
+++ backend/app/adapters.py
@@ -522,7 +523,7 @@
                 time=_time_at(0), value=_synthetic_value("temperature", lat, lon, d, 0) + random.uniform(-0.5, 0.5),
                 unit="degC", platform_id=pid, platform_type="argo",
-                data_status="DEMONSTRATION DATA", source_organization="Synthetic Generator"
+                data_source="synthetic", source_organization="Synthetic Generator"
             ))
     return records
```

## 4. adapters.py: Fix `BathymetryAdapter` (Point 3)
```diff
--- backend/app/adapters.py
+++ backend/app/adapters.py
@@ -193,12 +193,13 @@
     def metadata(self) -> dict:
         import os
         has_file = (BASE_DIR / "sample_bathymetry_gebco.nc").exists()
-        status = "CACHED REAL DATA" if has_file else "DEMONSTRATION DATA"
+        source = "cached" if has_file else "unavailable"
         return {
             "source_name": "GEBCO_2023_GRID Global Ocean Bathymetry",
             "variables": self.VARIABLES,
             "units": self.UNITS,
             "platform_type": None,
-            "data_status": status,
+            "data_source": source,
+            "data_status": "CACHED REAL DATA" if has_file else "UNAVAILABLE",
             "source_organization": "GEBCO (General Bathymetric Chart of the Oceans)",
             "product_id": "GEBCO_2023_GRID",
```

## 5. adapters.py: Shared Helper Updates (Point 4 - Audit)
```diff
--- backend/app/adapters.py
+++ backend/app/adapters.py
@@ -266,7 +266,8 @@
                                 unit=units.get(var, "unknown"),
                                 source_model=source_org,
                                 source_file=filepath,
-                                data_status=data_status,
+                                data_source="cached",
+                                data_status="CACHED REAL DATA",
                                 source_organization=source_org,
                                 product_id=product_id,
                                 retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
@@ -298,7 +299,8 @@
                             value=_synthetic_value(var, lat, lon, depth, step),
                             unit=units[var],
                             source_model=source_org,
                             source_file="global_grid",
-                            data_status=data_status,
+                            data_source="synthetic",
+                            data_status="DEMONSTRATION DATA",
                             source_organization=source_org,
                             product_id=product_id,
                             retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
```
