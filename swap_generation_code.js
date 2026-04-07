/***** AUTO-SWAP GENERATION — coller à la suite dans Code.gs *****/


/**
 * Génère les swaps automatiquement à partir des anomalies détectées.
 * Pour chaque anomalie, cherche une carte de remplacement dans le même tier/rareté
 * avec une valeur cohérente (entre le rang au-dessus et en-dessous).
 */
function generateSwapsFromAnomalies(anomalies, src) {
  var range = src.getDataRange();
  var values = range.getValues();
  var displays = range.getDisplayValues();
  var header = values[0].map(function(h) { return String(h).trim().toLowerCase(); });

  var COL = {
    rarity: header.indexOf('rarity'),
    tier: header.indexOf('tier'),
    slug: header.indexOf('slug'),
    rank: header.indexOf('rank'),
    rewarded_ranks: header.indexOf('rewarded_ranks'),
    rewarded_rewardables: header.indexOf('rewarded_rewardables'),
    limited_value: header.indexOf('limited_value')
  };

  var rows = values.slice(1);
  var rowsDisp = displays.slice(1);

  // ── 1. Catalogue : rarity|tier → [{slug, value}] trié par valeur desc ──
  var catalog = new Map();
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var rowD = rowsDisp[i];
    var rarity = normRarity(row[COL.rarity]);
    if (!CONFIG.ALLOWED_RARITIES.includes(rarity)) continue;

    var tier = String(row[COL.tier] || '').trim();
    var slug = String(row[COL.slug] || '').trim();

    var value = null;
    for (var k = 0; k < CONFIG.VALUE_COL_SPAN; k++) {
      var v = toNumber(rowD[COL.limited_value + k]);
      if (Number.isFinite(v)) { value = v; break; }
    }
    if (!slug || !isCleanValue(value)) continue;

    var catKey = rarity + '|' + tier;
    if (!catalog.has(catKey)) catalog.set(catKey, []);
    catalog.get(catKey).push({ slug: slug, value: value });
  }
  for (var entry of catalog) {
    entry[1].sort(function(a, b) { return b.value - a.value; });
  }

  // ── 2. Assignments : rarity|division|managerRank → {cardSlug, value, leaderboardSlug, tier} ──
  var assignments = new Map();
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var rowD = rowsDisp[i];
    var rarity = normRarity(row[COL.rarity]);
    if (!CONFIG.ALLOWED_RARITIES.includes(rarity)) continue;

    var tier = String(row[COL.tier] || '').trim();
    var slug = String(row[COL.slug] || '').trim();

    var value = null;
    for (var k = 0; k < CONFIG.VALUE_COL_SPAN; k++) {
      var v = toNumber(rowD[COL.limited_value + k]);
      if (Number.isFinite(v)) { value = v; break; }
    }

    var ranksStr = String(row[COL.rewarded_ranks] || '').trim();
    var rewardablesStr = String(row[COL.rewarded_rewardables] || '').trim();
    if (!ranksStr || !rewardablesStr) continue;

    var ranks = ranksStr.split(',').map(function(r) { return Number(r.trim()); }).filter(Number.isFinite);
    var rewardables = rewardablesStr.split(',').map(function(r) { return r.trim(); }).filter(Boolean);

    for (var j = 0; j < Math.min(ranks.length, rewardables.length); j++) {
      var divMatch = rewardables[j].match(/division-(\d)/);
      if (!divMatch) continue;
      var div = Number(divMatch[1]);
      var assignKey = rarity + '|' + div + '|' + ranks[j];
      assignments.set(assignKey, {
        cardSlug: slug,
        value: isCleanValue(value) ? value : null,
        leaderboardSlug: rewardables[j],
        tier: tier
      });
    }
  }

  // ── 3. Collecter les rangs anomaliques pour éviter de se baser sur un rang erroné ──
  var anomalousRanks = new Set();
  for (var a0 = 0; a0 < anomalies.length; a0++) {
    var an = anomalies[a0];
    if (an.type === 'INTRA_DIV_RANK_INVERSION') {
      var m0 = an.cas.match(/\[(\w+)\]\s*D(\d+)-R(\d+)\s*vs\s*D(\d+)-R(\d+)/);
      if (m0) {
        // Le rang "worse" (numéro élevé) est celui dont la valeur est trop haute
        anomalousRanks.add(m0[1] + '|' + m0[2] + '|' + m0[3]);
      }
    }
  }

  // ── 4. Générer les swaps ──
  var swaps = [];
  var usedReplacements = new Set();

  for (var a = 0; a < anomalies.length; a++) {
    var anomaly = anomalies[a];

    if (anomaly.type === 'INTRA_DIV_RANK_INVERSION') {
      // Parse: [rarity] D{div}-R{rankWorse} vs D{div}-R{rankBetter}
      var m = anomaly.cas.match(/\[(\w+)\]\s*D(\d+)-R(\d+)\s*vs\s*D(\d+)-R(\d+)/);
      if (!m) continue;

      var rarity = m[1];
      var div = Number(m[2]);
      var rankWorse = Number(m[3]);   // rang inférieur (numéro plus élevé)
      var rankBetter = Number(m[5]);  // rang supérieur (numéro plus bas)

      var worseAssign = assignments.get(rarity + '|' + div + '|' + rankWorse);
      if (!worseAssign) continue;

      // Remonter jusqu'au premier rang "sain" (non anomalique) pour la borne haute
      var maxVal = null;
      for (var r = rankBetter; r >= 1; r--) {
        var rKey = rarity + '|' + div + '|' + r;
        if (!anomalousRanks.has(rKey)) {
          var cleanAssign = assignments.get(rKey);
          if (cleanAssign && isCleanValue(cleanAssign.value)) {
            maxVal = cleanAssign.value;
            break;
          }
        }
      }
      if (maxVal === null) {
        swaps.push({
          so5_leaderboard_slug: worseAssign ? worseAssign.leaderboardSlug : '?',
          ranking: rankWorse,
          rarity: rarity,
          current_player_slug: worseAssign ? worseAssign.cardSlug : '?',
          substitute_player_slug: '⚠ NO SWAP',
          serial_number: '',
          custom_card_edition_name: '',
          current_value: worseAssign ? worseAssign.value : '?',
          substitute_value: 'Aucun rang sain trouvé au-dessus',
          debug: 'D' + div + '-R' + rankBetter + ' non trouvé dans assignments'
        });
        continue;
      }

      // Descendre jusqu'au premier rang "sain" pour la borne basse
      var minVal = 0;
      for (var r2 = rankWorse + 1; r2 <= rankWorse + 20; r2++) {
        var rKey2 = rarity + '|' + div + '|' + r2;
        if (!anomalousRanks.has(rKey2)) {
          var cleanAssign2 = assignments.get(rKey2);
          if (cleanAssign2 && isCleanValue(cleanAssign2.value)) {
            minVal = cleanAssign2.value;
            break;
          }
        }
      }

      // Si la borne basse est supérieure à la borne haute, ignorer la borne basse
      if (minVal > maxVal) minVal = 0;

      // Chercher un remplacement dans le même tier
      var tierKey = rarity + '|' + worseAssign.tier;
      var tierCards = catalog.get(tierKey) || [];
      var replacement = null;
      for (var c = 0; c < tierCards.length; c++) {
        var card = tierCards[c];
        if (card.value <= maxVal && card.value >= minVal &&
            card.slug !== worseAssign.cardSlug &&
            !usedReplacements.has(rarity + '|' + card.slug)) {
          replacement = card;
          break;
        }
      }

      if (replacement) {
        usedReplacements.add(rarity + '|' + replacement.slug);
        swaps.push({
          so5_leaderboard_slug: worseAssign.leaderboardSlug,
          ranking: rankWorse,
          rarity: rarity,
          current_player_slug: worseAssign.cardSlug,
          substitute_player_slug: replacement.slug,
          serial_number: '',
          custom_card_edition_name: '',
          current_value: worseAssign.value,
          substitute_value: replacement.value,
          debug: ''
        });
      } else {
        swaps.push({
          so5_leaderboard_slug: worseAssign.leaderboardSlug,
          ranking: rankWorse,
          rarity: rarity,
          current_player_slug: worseAssign.cardSlug,
          substitute_player_slug: '⚠ NO SWAP',
          serial_number: '',
          custom_card_edition_name: '',
          current_value: worseAssign.value,
          substitute_value: 'Fourchette: ' + minVal + ' - ' + maxVal + ' | Tier: ' + worseAssign.tier + ' | Cards dispo: ' + tierCards.length,
          debug: tierKey
        });
      }
    }

    if (anomaly.type === 'INTER_DIV_SAME_RANK_INVERSION') {
      // Parse: [rarity] R{rank}: D{divWorse} vs D{divBetter}
      var m2 = anomaly.cas.match(/\[(\w+)\]\s*R(\d+):\s*D(\d+)\s*vs\s*D(\d+)/);
      if (!m2) continue;

      var rarity2 = m2[1];
      var rank2 = Number(m2[2]);
      var divWorse2 = Number(m2[3]);   // division inférieure (D2 ou D3)
      var divBetter2 = Number(m2[4]);  // division supérieure (D1)

      var worseAssign2 = assignments.get(rarity2 + '|' + divWorse2 + '|' + rank2);
      var betterAssign2 = assignments.get(rarity2 + '|' + divBetter2 + '|' + rank2);
      if (!worseAssign2 || !betterAssign2) continue;

      var maxVal2 = betterAssign2.value;
      var tierCards2 = catalog.get(rarity2 + '|' + worseAssign2.tier) || [];
      var replacement2 = null;
      for (var c2 = 0; c2 < tierCards2.length; c2++) {
        var card2 = tierCards2[c2];
        if (card2.value <= maxVal2 &&
            card2.slug !== worseAssign2.cardSlug &&
            !usedReplacements.has(rarity2 + '|' + card2.slug)) {
          replacement2 = card2;
          break;
        }
      }

      if (replacement2) {
        usedReplacements.add(rarity2 + '|' + replacement2.slug);
        swaps.push({
          so5_leaderboard_slug: worseAssign2.leaderboardSlug,
          ranking: rank2,
          rarity: rarity2,
          current_player_slug: worseAssign2.cardSlug,
          substitute_player_slug: replacement2.slug,
          serial_number: '',
          custom_card_edition_name: '',
          current_value: worseAssign2.value,
          substitute_value: replacement2.value
        });
      }
    }
  }

  return swaps;
}


/**
 * Écrit les swaps dans un nouvel onglet "Swaps - {source}".
 * Les 7 premières colonnes = format CSV d'upload admin.
 * Les 2 dernières (current_value, substitute_value) = pour vérification visuelle.
 */
function writeSwapsSheet(ss, swaps, sourceName) {
  var sheetName = 'Swaps - ' + sourceName;
  var sh = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
  sh.clear();

  var header = [
    'so5_leaderboard_slug', 'ranking', 'rarity',
    'current_player_slug', 'substitute_player_slug',
    'serial_number', 'custom_card_edition_name',
    'current_value (info)', 'substitute_value (info)', 'debug'
  ];
  sh.getRange(1, 1, 1, header.length).setValues([header]).setFontWeight('bold');

  if (swaps.length) {
    var rows = swaps.map(function(s) {
      return [
        s.so5_leaderboard_slug, s.ranking, s.rarity,
        s.current_player_slug, s.substitute_player_slug,
        s.serial_number, s.custom_card_edition_name,
        s.current_value, s.substitute_value, s.debug || ''
      ];
    });
    sh.getRange(2, 1, rows.length, header.length).setValues(rows);
  }

  sh.autoResizeColumns(1, header.length);
  return sh;
}
