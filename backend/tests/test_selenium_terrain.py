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
        options.add_argument('--use-gl=angle')

        driver = webdriver.Edge(options=options)
        try:
            driver.get('http://localhost:5500')
            time.sleep(6)

            driver.save_screenshot('screenshot_A_india_ocean.png')
            print('Saved SCREENSHOT A: screenshot_A_india_ocean.png')

            himalaya_btn = driver.find_element(By.ID, 'btnFlyHimalayas')
            himalaya_btn.click()
            time.sleep(5)

            driver.save_screenshot('screenshot_B_himalayas.png')
            print('Saved SCREENSHOT B: screenshot_B_himalayas.png')

            is_cesium_terrain = driver.execute_script('return viewer ? (viewer.terrainProvider instanceof Cesium.CesiumTerrainProvider) : false;')
            ion_status = driver.execute_script('return state ? state.cesiumIonStatus : "None";')
            world_terrain_loaded = driver.execute_script('return state ? state.worldTerrainLoaded : false;')

            print('========================================')
            print('RUNTIME VERIFICATION RESULTS:')
            print('Is CesiumTerrainProvider Instance:', is_cesium_terrain)
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
