"""
Selenium Browser Runtime Test for Interactive Sea-Level Simulation Feature.
"""
import os
import sys
import time
import subprocess
import unittest
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By


class TestSeaLevelSimulationRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start backend on 8000
        cls.backend_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Start frontend on 5500
        cls.frontend_proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", "5500", "--directory", "../frontend"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(3)

    @classmethod
    def tearDownClass(cls):
        cls.backend_proc.terminate()
        cls.frontend_proc.terminate()

    def test_sealevel_slider_and_analytics(self):
        options = EdgeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--enable-webgl')
        options.add_argument('--use-gl=angle')

        driver = webdriver.Edge(options=options)
        try:
            driver.get('http://localhost:5500')
            time.sleep(4)

            # Wait for heightmap data to finish loading
            for _ in range(30):
                loaded = driver.execute_script('return state && state.etopoElevations ? state.etopoElevations.length : 0;')
                if loaded > 0:
                    break
                time.sleep(0.5)

            # Open Sea Level Panel
            driver.execute_script('openSeaLevelPanel();')
            time.sleep(1)

            # Change sea level to +25m via script / UI
            driver.execute_script('setSeaLevelValue(25);')
            time.sleep(1)

            sl_val_25 = driver.execute_script('return state.seaLevelMeters;')
            affected_km2_25 = driver.execute_script('return state.affectedAreaKm2;')
            self.assertEqual(sl_val_25, 25)
            self.assertGreater(affected_km2_25, 0)

            # Check display element text
            disp_text = driver.find_element(By.ID, 'slDisplayValue').text
            self.assertEqual(disp_text, '+25 m')

            # Change sea level to -10m
            driver.execute_script('setSeaLevelValue(-10);')
            time.sleep(1)

            sl_val_neg10 = driver.execute_script('return state.seaLevelMeters;')
            affected_km2_neg10 = driver.execute_script('return state.affectedAreaKm2;')
            self.assertEqual(sl_val_neg10, -10)
            self.assertGreater(affected_km2_neg10, 0)

            disp_text_neg = driver.find_element(By.ID, 'slDisplayValue').text
            self.assertEqual(disp_text_neg, '-10 m')

            # Reset sea level to 0m
            driver.execute_script('setSeaLevelValue(0);')
            time.sleep(1)
            self.assertEqual(driver.execute_script('return state.seaLevelMeters;'), 0)
            self.assertEqual(driver.execute_script('return state.affectedAreaKm2;'), 0)

            # Test switching to 3D Earth Without Water Physical Relief Globe
            driver.execute_script('switchGlobeView("relief");')
            time.sleep(1)

            view_mode = driver.execute_script('return state ? state.globeViewMode : null;')
            self.assertEqual(view_mode, "relief")

            # Fly to Mid-Atlantic Ridge 3D Feature
            driver.execute_script('flyToRidge();')
            time.sleep(1)

            # Fly to Mariana Trench 3D Feature
            driver.execute_script('flyToMariana();')
            time.sleep(1)

            # Switch back to Cesium Satellite View
            driver.execute_script('switchGlobeView("cesium");')
            time.sleep(1)
            self.assertEqual(driver.execute_script('return state.globeViewMode;'), "cesium")

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
