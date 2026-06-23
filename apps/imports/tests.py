import os
import tempfile

import pandas as pd
from django.test import SimpleTestCase

from .services import _sheet_exists


class ImportServicesTests(SimpleTestCase):
    def test_sheet_exists_closes_temp_file(self):
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        df = pd.DataFrame({'A': [1, 2, 3]})
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

        self.assertTrue(_sheet_exists(path, 'Sheet1'))

        os.remove(path)
        self.assertFalse(os.path.exists(path))
