from celery.contrib.methods import task

from lib.constants import DATASET_ID, ERROR
from lib.exceptions import ParseError
from lib.parser import Parser, ParserContext
from lib.tasks.calculator import Calculator
from models.abstract_model import AbstractModel
from models.dataset import Dataset
from models.observation import Observation


class Calculation(AbstractModel):

    __collectionname__ = 'calculations'
    parser = Parser()

    FORMULA = 'formula'
    GROUP = 'group'
    NAME = 'name'
    QUERY = 'query'

    @property
    def dataset_id(self):
        return self.record[DATASET_ID]

    @property
    def name(self):
        return self.record[self.NAME]

    @task
    def delete(self):
        dataset = Dataset.find_one(self.dataset_id)
        dframe = Observation.find(dataset, as_df=True)
        slug = dataset.build_labels_to_slugs()[self.name]
        del dframe[slug]
        Observation.update(dframe, dataset)
        super(self.__class__, self).delete({
            DATASET_ID: self.dataset_id,
            self.NAME: self.name
        })

    def save(self, dataset, formula, name, group=None):
        """
        Attempt to parse formula, then save formula, and add a task to
        calculate formula.
        """
        calculator = Calculator(dataset)

        # ensure that the formula is parsable
        try:
            calculator.validate(formula, group)
        except ParseError, err:
            # do not save record, return error
            return {ERROR: err}

        record = {
            DATASET_ID: dataset.dataset_id,
            self.FORMULA: formula,
            self.GROUP: group,
            self.NAME: name,
        }
        self.collection.insert(record, safe=True)

        dataset.clear_summary_stats()

        # call async calculate
        calculator.calculate_column.delay(calculator, formula, name, group)

        self.record = record
        return self.record

    @classmethod
    def find_one(cls, dataset_id, name):
        return super(cls, cls).find_one({
            DATASET_ID: dataset_id,
            cls.NAME: name,
        })

    @classmethod
    def find(cls, dataset):
        return super(cls, cls).find({DATASET_ID: dataset.dataset_id})

    @classmethod
    def update(cls, dataset, data):
        """
        Update *dataset* with new *data*.
        """
        calculations = Calculation.find(dataset)
        calculator = Calculator(dataset)
        calculator.calculate_updates.delay(
            calculator, data, calculations, cls.FORMULA)
