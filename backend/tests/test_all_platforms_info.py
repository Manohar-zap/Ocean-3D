"""
Test right-side panel depth and parameters for ARGO, GLIDER, CTD, and BGC platforms.
"""
import time
import unittest
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions


class TestAllPlatformsRightPanel(unittest.TestCase):
    def test_all_platforms_info_panel(self):
        options = EdgeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--enable-webgl')
        options.add_argument('--use-gl=angle')

        driver = webdriver.Edge(options=options)
        try:
            driver.get('http://localhost:5500')
            time.sleep(5)

            target_types = ['argo', 'glider', 'ctd', 'bgc']
            pids = []
            for t in target_types:
                found_id = driver.execute_script(f"""
                    let entity = profileEntities.find(e => e.userData && e.userData.platform_type === '{t}');
                    return entity ? entity.userData.platform_id : null;
                """)
                if found_id:
                    pids.append(found_id)

            for pid in pids:
                driver.execute_script(f"openProfile('{pid}');")
                time.sleep(2)

                obs_id = driver.execute_script("return document.getElementById('obsPlatformId').textContent;")
                obs_type = driver.execute_script("return document.getElementById('obsType').textContent;")
                obs_depth = driver.execute_script("return document.getElementById('obsDepth').textContent;")
                obs_temp = driver.execute_script("return document.getElementById('obsTemp').textContent;")
                obs_sal = driver.execute_script("return document.getElementById('obsSal').textContent;")

                print(f'Platform {pid} -> ID: {obs_id}, Type: {obs_type}, Depth: {obs_depth}, Temp: {obs_temp}, Sal: {obs_sal}')

                self.assertEqual(obs_id, pid)
                self.assertIn('m', obs_depth)
                self.assertNotEqual(obs_depth, '--')

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
