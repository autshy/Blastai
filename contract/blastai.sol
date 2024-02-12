// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";


interface IBlast {
    function configureClaimableYield() external;
    function configureClaimableGas() external;
    function claimYield(address contractAddress, address recipientOfYield, uint256 amount) external returns (uint256);
    function claimAllYield(address contractAddress, address recipientOfYield) external returns (uint256);
    function claimAllGas(address contractAddress, address recipient) external returns (uint256);
    function claimMaxGas(address contractAddress, address recipient) external returns (uint256);

}


contract Blastai is ERC721, ERC721Enumerable, ERC721URIStorage {
    uint256 private _nextTokenId = 1;
    uint256 public constant MAX_SUPPLY = 10000;
    string public baseURI;
    address public owner;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not the owner");
        _;
    }

    struct Profile {
        uint256 lastActiveTime;
        mapping(address => uint256) preferredTokenIndexes;
        address[] preferredTokens;
        string[] preferredNFTTypes;
    }

    mapping(address => Profile) private _userProfiles;
    mapping(address => mapping(address => uint256)) private _userTokenCounts;
    mapping(address => mapping(string => uint256)) private _userNFTTypeCounts;
    address public constant blastContract = 0x4300000000000000000000000000000000000002;

    event HashComputed(address indexed sender, bytes32 hash);


    constructor()
        ERC721("Blastai", "Blastai")
    {
        owner = msg.sender;
        IBlast(blastContract).configureClaimableYield();
        IBlast(blastContract).configureClaimableGas();
    }

    // Users can upload important informations to blastai
    function recordinfo(string memory input) external {
        bytes32 hash = sha256(abi.encodePacked(input));
        emit HashComputed(msg.sender, hash);
        payable(msg.sender).transfer(0);
    }

    // The following functions are about blastai NFT
    function setBaseURI(string memory newBaseURI) external onlyOwner  {
        baseURI = newBaseURI;
    }

    function safeMint(address to) public  {
        uint256 tokenId = _nextTokenId++;
        require(_nextTokenId <= MAX_SUPPLY, "I'm sorry we reached the cap");
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, baseURI);
    }

    // The following functions are overrides required by Solidity.

    function _update(address to, uint256 tokenId, address auth)
        internal
        override(ERC721, ERC721Enumerable)
        returns (address)
    {
        return super._update(to, tokenId, auth);
    }

    function _increaseBalance(address account, uint128 value)
        internal
        override(ERC721, ERC721Enumerable)
    {
        super._increaseBalance(account, value);
    }

    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721Enumerable, ERC721URIStorage)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }


    // The following functions are about  Personalized Recommendation
     // setLastActiveTime
    function setLastActiveTime(uint256 time) public {
        _userProfiles[msg.sender].lastActiveTime = time;
    }

    // getLastActiveTime
    function getLastActiveTime(address user) public view returns (uint256) {
        return _userProfiles[user].lastActiveTime;
    }

    // addPreferredToken
    function addPreferredToken(address token) public {
        Profile storage profile = _userProfiles[msg.sender];
        if (profile.preferredTokenIndexes[token] == 0) {
            profile.preferredTokens.push(token);
            profile.preferredTokenIndexes[token] = profile.preferredTokens.length;
        }
    }
    // analyzePreferredTokens
    function analyzePreferredTokens(address[] memory tokens) public {
        for (uint256 i = 0; i < tokens.length; i++) {
            _userTokenCounts[msg.sender][tokens[i]]++;
        }
    }

    // getPreferredTokens
    function getPreferredTokens(address user) public view returns (address[] memory) {
        Profile storage profile = _userProfiles[user];
        return profile.preferredTokens;
    }

    // addPreferredNFTType
    function addPreferredNFTType(string memory nftType) public {
        Profile storage profile = _userProfiles[msg.sender];
        profile.preferredNFTTypes.push(nftType);
    }

    // analyzePreferredNFTTypes
    function analyzePreferredNFTTypes(address user, string[] memory nftTypes) public {
        for (uint256 i = 0; i < nftTypes.length; i++) {
            _userNFTTypeCounts[user][nftTypes[i]]++;
        }
    }

    // getPreferredNFTTypes
    function getPreferredNFTTypes(address user) public view returns (string[] memory) {
        Profile storage profile = _userProfiles[user];
        return profile.preferredNFTTypes;
    }


    // The following functions are about Blast refund
    function claimAllGas() external onlyOwner {
        IBlast(blastContract).claimAllGas(address(this), msg.sender);
    }

    function claimMaxGas() external onlyOwner {
        IBlast(blastContract).claimMaxGas(address(this), msg.sender);
    }


    function claimAllYield(address recipient) external onlyOwner {
		IBlast(blastContract).claimAllYield(address(this), recipient);
  }

    function claimYield(address recipient,uint256 amount) external onlyOwner {
        IBlast(blastContract).claimYield(address(this), recipient, amount);
    }


}