"""
Selenium Verification Test for 3D Temperature Slices on Globe across Depth Levels.
"""
import time
import unittest
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions


class Test3DTemperatureSlices(unittest.TestCase):
    def test_temperature_depth_slice_transitions(self):
        options = EdgeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1600,1000')
        options.add_argument('--enable-webgl')
        options.add_argument('--use-gl=angle')

        driver = webdriver.Edge(options=options)
        try:
            driver.get('http://localhost:5500')
            time.sleep(6) # Wait for surface temperature field rendering on globe

            # Screenshot 1: Surface Temperature (0m)
            driver.save_screenshot('screenshot_temp_0m.png')
            print('Saved Surface Temperature (0m) screenshot: screenshot_temp_0m.png')

            model_entities_count_0m = driver.execute_script('return modelEntities ? modelEntities.length : 0;')
            print(f'Surface 0m Temperature Entities Count: {model_entities_count_0m}')
            self.assertGreater(model_entities_count_0m, 0)

            # Move depth slider to index 9 (500m)
            driver.execute_script("document.getElementById('depthSlider').value = 9; document.getElementById('depthSlider').dispatchEvent(new Event('input'));")
            time.sleep(4)

            # Screenshot 2: 500m Temperature Field
            driver.save_screenshot('screenshot_temp_500m.png')
            print('Saved 500m Temperature Field screenshot: screenshot_temp_500m.png')

            depth_label_500m = driver.execute_script("return document.getElementById('depthLabel').textContent;")
            self.assertEqual(depth_label_500m, '500 m')

            # Move depth slider to index 11 (1000m)
            driver.execute_script("document.getElementById('depthSlider').value = 11; document.getElementById('depthSlider').dispatchEvent(new Event('input'));")
            time.sleep(4)

            # Screenshot 3: 1000m Temperature Field
            driver.save_screenshot('screenshot_temp_1000m.png')
            print('Saved 1000m Temperature Field screenshot: screenshot_temp_1000m.png')

            depth_label_1000m = driver.execute_script("return document.getElementById('depthLabel').textContent;")
            self.assertEqual(depth_label_1000m, '1000 m')

            # Verify Cesium entities actively rendered on globe
            model_entities_count_1000m = driver.execute_script('return modelEntities ? modelEntities.length : 0;')
            print(f'1000m Temperature Entities Count: {model_entities_count_1000m}')
            self.assertGreater(model_entities_count_1000m, 0)

        finally:
            driver.quit()


if __name__ == '__main__':
    unittest.main()
