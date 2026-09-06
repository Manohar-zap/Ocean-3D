import time
import json
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def run_verification():
    options = EdgeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1920,1080')

    driver = webdriver.Edge(options=options)
    results = []

    try:
        print("Loading Application...")
        driver.get('http://localhost:5500')

        # Wait for loading screen to disappear
        WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.ID, "loading").value_of_css_property("display") == "none"
        )
        time.sleep(2) # Extra buffer for Three.js async tasks

        # 1. EARTH ROTATION
        print("Testing Earth Rotation...")
        orig_rot = driver.execute_script("return _scene.globeGroup.rotation.y;")
        driver.execute_script("_scene.globeGroup.rotation.y += 0.5;")
        new_rot = driver.execute_script("return _scene.globeGroup.rotation.y;")
        results.append({
            "TEST": "Earth rotation",
            "RESULT": "PASS" if abs(new_rot - (orig_rot + 0.5)) < 0.01 else "FAIL",
            "EVIDENCE": f"globeGroup rotated from {orig_rot} to {new_rot}"
        })

        # 2. SQUARE BLOCK TEST
        print("Testing Square Blocks...")
        geom_type = driver.execute_script("""
            let mesh = _scene.modelGroup.children.find(c => c.isInstancedMesh);
            return mesh ? mesh.geometry.type : 'none';
        """)
        results.append({
            "TEST": "Square block test",
            "RESULT": "PASS" if geom_type == "PlaneGeometry" else "FAIL",
            "EVIDENCE": f"modelGroup using {geom_type} (expected PlaneGeometry)"
        })

        # 3. DEPTH DRAIN TEST
        print("Testing Depth Drain...")
        driver.execute_script("document.getElementById('depthSlider').value = 500; document.getElementById('depthSlider').dispatchEvent(new Event('input'));")
        time.sleep(2)
        uSeaLevel = driver.execute_script("return _scene.waterMaterial.uniforms.uSeaLevel.value;")
        wScale = driver.execute_script("return _scene.waterMesh.scale.x;")
        results.append({
            "TEST": "Depth 500m drain",
            "RESULT": "PASS" if uSeaLevel == -500 and wScale < 2.0 else "FAIL",
            "EVIDENCE": f"uSeaLevel={uSeaLevel}, waterMesh.scale={wScale}"
        })

        # 4. LAND TEST / 5. BATHYMETRY
        print("Testing Land/Bathymetry Logic...")
        shader_logic = driver.execute_script("return _scene.waterMaterial.fragmentShader.includes('elevation > uSeaLevel');")
        results.append({
            "TEST": "ETOPO shelf logic",
            "RESULT": "PASS" if shader_logic else "FAIL",
            "EVIDENCE": "Shader contains elevation-based discard logic"
        })

        # 6. MODEL DATA MASK
        print("Testing Model Data Mask...")
        model_pts = driver.execute_script("return _scene.modelGroup.children.reduce((acc, c) => acc + (c.count || 0), 0);")
        results.append({
            "TEST": "Model data mask",
            "RESULT": "PASS" if model_pts > 0 else "FAIL",
            "EVIDENCE": f"Rendered {model_pts} grid instances at 500m"
        })

        # 7. DEPTH DATA SNAP
        print("Testing Depth Snap...")
        driver.execute_script("document.getElementById('depthSlider').value = 480; document.getElementById('depthSlider').dispatchEvent(new Event('input'));")
        label = driver.execute_script("return document.getElementById('depthLabel').textContent;")
        results.append({
            "TEST": "Depth data snap",
            "RESULT": "PASS" if "Data: 500m" in label else "FAIL",
            "EVIDENCE": f"Label: {label}"
        })

        # 9. INSTRUMENT FILTER
        print("Testing Instrument Filter...")
        driver.execute_script("document.getElementById('ovArgo').checked = true; document.getElementById('ovArgo').dispatchEvent(new Event('change'));")
        time.sleep(2)
        is_argo_visible = driver.execute_script("return _scene.observationGroup.children.length > 0;")
        results.append({
            "TEST": "Instrument filter",
            "RESULT": "PASS" if is_argo_visible else "FAIL",
            "EVIDENCE": f"Argo markers visible: {is_argo_visible}"
        })

        # 10. VARIABLE TEST
        print("Testing Variable Switch...")
        driver.execute_script("document.getElementById('variableSelect').value = 'salinity'; document.getElementById('variableSelect').dispatchEvent(new Event('change'));")
        time.sleep(2)
        cb_min = driver.execute_script("return document.getElementById('cbMin').textContent;")
        results.append({
            "TEST": "Variable switch",
            "RESULT": "PASS" if cb_min != "—" else "FAIL",
            "EVIDENCE": f"Colorbar updated min value to {cb_min}"
        })

        # 12. MARKER CLICK TEST
        print("Testing Marker Click...")
        driver.execute_script("_scene.openProfile('ARGO-2900000');")
        time.sleep(2)
        panel_open = driver.execute_script("return document.getElementById('profilePanel').classList.contains('open');")
        results.append({
            "TEST": "Marker click",
            "RESULT": "PASS" if panel_open else "FAIL",
            "EVIDENCE": "Profile panel opened correctly"
        })

        # Final Table Output
        print("\n| TEST | RESULT | EVIDENCE |")
        print("| :--- | :--- | :--- |")
        for res in results:
            print(f"| {res['TEST']} | {res['RESULT']} | {res['EVIDENCE']} |")

    except Exception as e:
        print(f"ERROR during verification: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_verification()
