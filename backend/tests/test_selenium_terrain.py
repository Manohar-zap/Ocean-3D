"""
Selenium Browser Runtime Test for Cesium World Terrain Verification.
"""
import time
import unittest
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By


class TestCesiumWorldTerrainRuntime(unittest.TestCase):
    def test_cesium_world_terrain(self):
        options = EdgeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--enable-webgl')
        options.add_argument('--ignore-gpu-blocklist')
        options.add_argument('--use-gl=angle')
        options.add_argument('--use-angle=swiftshader')

        driver = webdriver.Edge(options=options)
        try:
            try:
                driver.get('http://127.0.0.1:8000')
            except Exception as ex:
                print('Navigation error:', ex)
                driver.get('http://localhost:8000')
            time.sleep(6)

            driver.save_screenshot('screenshot_A_india_ocean.png')
            print('Saved SCREENSHOT A: screenshot_A_india_ocean.png')

            himalaya_btn = driver.find_element(By.ID, 'btnFlyHimalayas')
            himalaya_btn.click()
            time.sleep(5)

            driver.save_screenshot('screenshot_B_himalayas.png')
            print('Saved SCREENSHOT B: screenshot_B_himalayas.png')

            print('Browser console log:', driver.get_log('browser'))
            is_cesium_terrain = driver.execute_script('return (window.viewer && window.viewer.terrainProvider) ? true : false;')
            ion_status = driver.execute_script('return window.state ? window.state.cesiumIonStatus : "None";')
            world_terrain_loaded = driver.execute_script('return window.state ? window.state.worldTerrainLoaded : false;')

            print('========================================')
            print('RUNTIME VERIFICATION RESULTS:')
            print('Viewer Terrain Active:', is_cesium_terrain)
            print('Cesium Ion Status:', ion_status)
            print('World Terrain Loaded:', world_terrain_loaded)
            print('========================================')

            self.assertTrue(is_cesium_terrain)
            self.assertEqual(ion_status, 'SUCCESS')
            self.assertTrue(world_terrain_loaded)

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
