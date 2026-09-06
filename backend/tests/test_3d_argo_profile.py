"""
Selenium Test for Native 3D Argo/CTD/Glider Profile Visualization in Cesium Scene.
"""
import time
import unittest
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions


class Test3DObservationProfile(unittest.TestCase):
    def test_3d_argo_profile_rendering(self):
        options = EdgeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--enable-webgl')
        options.add_argument('--use-gl=angle')

        driver = webdriver.Edge(options=options)
        try:
            driver.get('http://localhost:5500')
            time.sleep(6) # Wait for Cesium Globe & 3D profile entities

            # Open profile for ARGO-2900000 in Cesium 3D scene
            driver.execute_script("openProfile('ARGO-2900000');")
            time.sleep(4)

            # Capture Screenshot of 3D ARGO Profile in Cesium 3D Scene
            screenshot_path = 'screenshot_3d_argo_profile.png'
            driver.save_screenshot(screenshot_path)
            print(f'Saved 3D ARGO profile screenshot to {screenshot_path}')

            # Verify 3D Depth Cursor entity exists in Cesium Viewer
            cursor_exists = driver.execute_script('return depthCursorEntity !== null;')
            print('3D Depth Cursor Entity Active:', cursor_exists)
            self.assertTrue(cursor_exists)

            # Move depth slider to index 9 (500m) -> verify 3D depth cursor moves in 3D scene
            driver.execute_script("document.getElementById('depthSlider').value = 9; document.getElementById('depthSlider').dispatchEvent(new Event('input'));")
            time.sleep(2)

            cursor_depth = driver.execute_script("return document.getElementById('obsCursorDepth').textContent;")
            print('Updated 3D Depth Cursor Depth:', cursor_depth)
            self.assertEqual(cursor_depth, '500 m')

            # Capture updated 3D Depth Cursor screenshot
            driver.save_screenshot('screenshot_3d_cursor_500m.png')
            print('Saved updated 3D Depth Cursor screenshot: screenshot_3d_cursor_500m.png')

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
