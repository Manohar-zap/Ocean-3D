"""
Test to verify land mask application on current vectors.
"""
import time
import unittest
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions


class TestCurrentVectorsLandMask(unittest.TestCase):
    def test_vectors_land_mask(self):
        options = EdgeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--enable-webgl')
        options.add_argument('--use-gl=angle')

        driver = webdriver.Edge(options=options)
        try:
            driver.get('http://localhost:5500')
            time.sleep(5)

            # Programmatically trigger Current Vectors toggle & render
            driver.execute_script("state.showVectors = true; document.getElementById('ovVectors').checked = true; loadVectors();")
            time.sleep(4)

            # Capture Screenshot of Current Vectors over Ocean
            screenshot_path = 'screenshot_vectors_land_masked.png'
            driver.save_screenshot(screenshot_path)
            print(f'Saved vector land mask screenshot to {screenshot_path}')

            # Verify entities in Cesium viewer
            vector_entities_count = driver.execute_script('return vectorEntities ? vectorEntities.length : 0;')
            print(f'Rendered Ocean Vector Polylines Count: {vector_entities_count}')

            # Out of 100 NetCDF grid coordinates, 25 land points are masked -> exactly 75 ocean vectors rendered over ocean!
            self.assertEqual(vector_entities_count, 75)

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
