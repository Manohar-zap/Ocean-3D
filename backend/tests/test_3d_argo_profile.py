"""
Selenium Test for Native 3D Argo/CTD/Glider Profile Visualization & Right Panel Info.
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

            # Query actual active ARGO platform ID from loaded map entities
            target_pid = driver.execute_script("""
                let entity = profileEntities.find(e => e.userData && e.userData.platform_type === 'argo');
                return entity ? entity.userData.platform_id : 'ARGO-2900000';
            """)

            driver.execute_script(f"openProfile('{target_pid}');")
            time.sleep(4)

            # Move depth slider to index 6 -> verify 3D depth cursor & right panel depth update
            driver.execute_script("document.getElementById('depthSlider').value = 6; document.getElementById('depthSlider').dispatchEvent(new Event('input'));")
            time.sleep(2)

            # Verify 3D Depth Cursor entity exists in Cesium Viewer
            cursor_exists = driver.execute_script('return depthCursorEntity !== null;')
            print('3D Depth Cursor Entity Active:', cursor_exists)
            self.assertTrue(cursor_exists)

            # Verify right-side panel observation depth & parameters
            obs_id = driver.execute_script("return document.getElementById('obsPlatformId').textContent;")
            obs_type = driver.execute_script("return document.getElementById('obsType').textContent;")
            obs_depth = driver.execute_script("return document.getElementById('obsDepth').textContent;")
            obs_temp = driver.execute_script("return document.getElementById('obsTemp').textContent;")
            obs_sal = driver.execute_script("return document.getElementById('obsSal').textContent;")

            print(f'Right Panel Info -> ID: {obs_id}, Type: {obs_type}, Depth: {obs_depth}, Temp: {obs_temp}, Sal: {obs_sal}')

            self.assertEqual(obs_id, target_pid)
            self.assertEqual(obs_type, 'ARGO')
            self.assertIn('m', obs_depth)
            self.assertNotEqual(obs_temp, '--')
            self.assertNotEqual(obs_sal, '--')

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
