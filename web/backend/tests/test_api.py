import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from evrp.core import load_instance, make_releases, solve_online
from web.backend.app import app, job_lock, jobs


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_instance_and_proof_endpoints(self):
        listed = self.client.get('/api/instances')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 9)
        self.assertEqual(listed.json()[0]['customers'], 10)
        detail = self.client.get('/api/instances/tc0c10s2cf1').json()
        self.assertEqual(detail['battery_wh'], 16000)
        self.assertEqual(len(detail['stations']), 2)
        proof = self.client.get('/api/proof/tc0c10s2cf1').json()
        self.assertAlmostEqual(sum(
            load_instance('tc0c10s2cf1').distance(a, b)
            for a, b in proof['mst_edges']), proof['mst_km'])
        self.assertLessEqual(proof['tour_km'], proof['upper_bound_km'] + 1e-8)

    def test_api_validation_and_experiment_rows(self):
        self.assertEqual(self.client.get('/api/instances/not-a-benchmark').status_code, 404)
        self.assertEqual(self.client.post('/api/runs', json={
            'instance': 'tc0c10s2cf1', 'seconds': 999, 'methods': ['greedy']}).status_code, 422)
        self.assertEqual(self.client.post('/api/runs', json={
            'instance': 'tc0c10s2cf1', 'methods': ['ga', 'ga']}).status_code, 422)
        rows = self.client.get('/api/experiments?instance=tc0c10s2cf1&dynamic_ratio=0.5')
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(len(rows.json()), 15)
        self.assertEqual(self.client.get('/api/runs/no-such-run').status_code, 404)
        with patch('web.backend.app.DEFAULT_ARCHIVE', Path('/missing/montoya.zip')):
            self.assertEqual(self.client.get('/api/instances/tc0c10s2cf1').status_code, 503)
        with job_lock:
            jobs['test-busy'] = {'status': 'running'}
        try:
            self.assertEqual(self.client.post('/api/runs', json={
                'instance': 'tc0c10s2cf1', 'methods': ['greedy']}).status_code, 409)
        finally:
            with job_lock:
                jobs.pop('test-busy', None)

    def test_job_trace_and_equal_release_schedules(self):
        response = self.client.post('/api/runs', json={
            'instance': 'tc0c10s2cf1', 'dynamic_ratio': 0.5, 'seed': 0,
            'seconds': 0.1, 'methods': ['greedy', 'ga', 'ga_vns']})
        self.assertEqual(response.status_code, 202)
        job_id = response.json()['id']
        for _ in range(100):
            job = self.client.get(f'/api/runs/{job_id}').json()
            if job['status'] != 'running':
                break
            time.sleep(0.05)
        self.assertEqual(job['status'], 'complete', job.get('error'))
        self.assertEqual(set(job['results']), {'greedy', 'ga', 'ga_vns'})
        schedules = [result['releases'] for result in job['results'].values()]
        self.assertEqual(schedules[0], schedules[1])
        self.assertEqual(schedules[1], schedules[2])
        for result in job['results'].values():
            self.assertEqual(result['served'], 10)
            self.assertEqual(len(result['snapshots']), len(result['replans']))
            self.assertEqual(result['snapshots'][0]['new_orders'], [1, 3, 5, 7, 10])
            self.assertTrue(any(v['committed'] for snapshot in result['snapshots'][1:]
                                for v in snapshot['vehicles'].values()))
        trace = job['results']['ga_vns']['snapshots'][0]['search']
        self.assertTrue(trace['generations'])
        self.assertIn('vns', trace['examples'])

    def test_trace_keeps_solution_metrics_when_budget_is_sufficient(self):
        instance = load_instance('tc0c10s2cf1')
        releases = make_releases(instance, 0.5, 0)
        plain = solve_online(instance, releases, 'ga_vns', 0, 2.0)
        traced = solve_online(instance, releases, 'ga_vns', 0, 2.0, include_trace=True)
        for key in ('served', 'vehicles', 'operating_hours', 'electricity_cost', 'wear_proxy_kwh'):
            self.assertAlmostEqual(plain[key], traced[key])


if __name__ == '__main__':
    unittest.main()
