import axios from 'axios';
import utils from '@/utils/utils';

export default {
  index() {
    return axios.get(utils.apiUrl('orchestrations'));
  },

  extract(extractor) {
    return axios.post(utils.apiUrl('orchestrations', `extract/${extractor}`));
  },

  installedPlugins() {
    return axios.get(utils.apiUrl('orchestrations', 'installed-plugins'));
  },

  load(extractor, loader) {
    return axios.post(utils.apiUrl('orchestrations', `load/${loader}`), {
      extractor,
    });
  },

  transform(model, connectionName) {
    return axios.post(utils.apiUrl('orchestrations', `transform/${model}`), {
      connection_name: connectionName,
    });
  },

  connectionNames() {
    return axios.get(utils.apiUrl('orchestrations', 'connection_names'));
  },

  run(payload) {
    return axios.post(utils.apiUrl('orchestrations', 'run'), payload);
  },
};
